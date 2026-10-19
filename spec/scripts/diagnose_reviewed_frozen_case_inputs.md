# Frozen40 source-input diagnostic

This diagnostic reuses the exact completed v182 development case identities,
without resampling, importing labels or resuming v182. It compares input
availability under two separate exact18-ref definition snapshots: default
HISTORY v6 and the already-used v12. Each matrix has40 cases ×18 references
=720 resolutions. Their results must never be pooled into a claimed default
Registry pass. The historical v182 Registry v11 is cohort provenance only.

## Source-owner preparation

`prepare(output)` is an offline source-owner operation. Verify the fixed whole
v182 input-envelope SHA, approved metadata SHA and acquisition-scope SHA before
reading the envelope. Extract only case_id, company_id, the original aware
prediction_time string, split name and original per-split order. Preserve all
16 Anchor,8 Evolution Validation and16 Discovery identities and their order;
reject duplicates, naive timestamps, unexpected splits or counts. Never read
individual ground_truth/basic_info fields or copy their values, labels, prose,
performance or prices. The old mixed envelope is opened/deserialized during
this explicit source-owner operation; do not claim that its bytes were never
accessed. No LabelStore or Locked Test file is opened.

Retain the origin binding, original schema/seed/before-model flag, approved
manifest identity and opaque Locked Test hash as control-plane provenance.
Verify those approved metadata identities without opening any approved split.
Map only these40 companies to CIK/ticker using the bound approved
acquisition_scope; that full3511-company scope is not a selected cohort.
No fallback, filtering, extra company/date expansion or current label-based
selection is permitted. Missing source material does not remove a case.

Write the local diagnostic `case-identities.json` projection and a separate
plan. This is not a new canonical business record or a reusable cohort schema.
Bind current code/spec/helpers, approved metadata/scope, completed periodic
source-review/input/result/view/original proof graph and both exact Registry
definition/skill sets. Preserve the completed653-document view; preparation
must not instantiate a global RawInfoStore or modify a historical Registry.

## Exact independent Registry scopes

The v6 authority is the default HISTORY v143 signals root, version6, exact
ordered18 references and definition hash. The v12 authority is the completed
periodic input plan's ordered18 references, version12 and definition hash.
Reconstruct each using production `snapshot_from_refs`, which supplies
definitions only and never imports retrospective profiles/stats or learning.
Reject source, ref, version or hash drift. Never replace an unknown version with
a current latest version. The two groups use separate runtime/output paths.

## Single source-only execution

`execute(output)` verifies the new plan and projection, including the origin's
whole-file SHA by streaming bytes only. It must not deserialize the old mixed
envelope or consume/output any outcome field. Record honestly that old mixed
file bytes were used for an authenticity hash. The exported projection is the
only case-data object deserialized by the execution consumer.

A durable exclusive execution-start marker makes any started stage terminal,
including partial failure. No retries, replacement root, completed reentry or
old-stage recovery is granted. Verify all bindings before opening the immutable
reviewed view; reconstruct one worker and verify full canonical restart/worker
equality. Preserve all source/view bytes; no global source store is constructed
or appended, and historical stages/Registry definitions remain unchanged.

For each of the original40 cutoffs, save the production default BasicInfo
bundle/model projection/lineage once. Preserve partial flags and omissions.
For each exact Registry group, call only `SignalExecutor.prepare_inputs` on all
18 references at every cutoff and persist all720 resolutions, exact source IDs,
coverage/period/observation fields and gaps. Cases outside the view or lacking
PIT source coverage remain in both matrices. Keep per-case fractions and the
existing0.8 comparison separate per group. No group borrows another's results.

Install the existing socket/model/Signal execution/fullprepare tripwires and
all public LabelStore reading-method tripwires during both operations. The
only research consumers are default BasicInfo projection and prepare_inputs.
No GET, external API, LLM, Signal apply, LabelStore read, fullprepare, label
recalculation or global source write occurs. This does not establish numeric
Signal validity, model behavior, Fast fitness, Locked-Test performance,
full-MVP completion or independent benefit. The old unproved48 claims remain
historical evidence, not this diagnostic's cohort or a new acceptance gate.
