# Frozen case scope and the offline/blind boundary

2026-10-20. The current fresh diagnostic has exactly40 cases:16 fixed Anchor,
8 Random from Evolution Validation and16 independent Discovery. Fast scores the
same24 Anchor+Random cases; Discovery is separate. This follows the architecture,
stage contract and actual per-stratum cap/append/stop loop, including the exact
historical runner bound to the failed source preflight. The loop cannot select
extra cases beyond those caps. Insufficient strata stop preparation.

The [native selection trace](../runs/diagnostics/case_scope_contract_20261020_v1/native-selection-review.json)
and [independent contract review](../runs/diagnostics/case_scope_contract_20261020_v1/blind-boundary-review.json)
show that the earlier48 claim was an unsupported diagnostic comment repeated in
reports. The original failure contains exactly16 Anchor exclusions and never
reaches later splits or writes a complete cohort manifest. Preserve those real
failures and historical files; do not invent an eight-case remainder, assign it
to LockedTest, or turn the old wording into a binding new acceptance denominator.
The earlier checks copied comments/counts instead of tracing the producer and
inspecting a real freeze. Merely adding configuration counts was also weaker
than checking the actual capped selection loop and persisted cohort.

The [actual metadata inspection](../runs/diagnostics/case_scope_contract_20261020_v1/root-metadata-inspection.json)
finds no input_manifest under the v143 default Registry source. A real completed
v182 input manifest does exist: schema diagnostic-development-subset-v1,
16/8/16 rows, seed42 and selection-before-model. Its approved hash matches the
current human-approved manifest, as does its opaque LockedTest hash. The original
Fast/Slow completion pointers remain1/1. Its Registryv11 is historical provenance;
it does not replace either the defaultv6 or separately reviewedv12 definitions.

There is no upper-level prohibition on an offline preparation owner handling
label-bearing development metadata for the existing stratified selection. The
blind Initialize/retrieval/apply/Reflect/Predictor paths exclude outcomes and
posthoc memory; LockedTest content stays sealed. The source-only stages' narrower
zero-access limits were experiment boundaries, not a new global policy. This
inspection deserialized a label-bearing frozen envelope inside the offline owner,
but selected or emitted no outcome values or basic_info prose. It did not read
the separate LabelStore or LockedTest files and did not call a model. A later
consumer must not be given the whole mixed envelope as its research input.

The approved manifest already binds a real acquisition_scope.json:3511 company
identities and five shared dates, with outcome_fields_included=false and
split_ownership_included=false. Its exact hash is verified. It is a provider
identity interface, not evidence of exact40 membership or permission to construct
a rectangular case library. Use it only to match identity metadata for the
original frozen cases; do not reconstruct or filter that cohort from labels,
source availability or the scope's wider issuer/date universe.

The next bounded diagnostic projects only the original ordered40 case IDs,
company IDs, aware prediction times and split positions. It copies no truth,
arbitrary metadata or basic_info. The source owner binds the original envelope;
authentication may stream its bytes for SHA, which must be disclosed rather than
called no file access. Source consumers deserialize only the projection. The
same653-document reviewed source view then supports two separate input matrices:
40x18 exactdefaultv6 and40x18 exactv12. Persist both full720 denominators, actual
BasicInfo projections, gaps and restore evidence. This neither changes the
research definition nor proves either Registry's measurements or the fullMVP.
No GET, model, Signalapply, LabelStore, fullprepare, global mutation or old-run
resume is authorized by this source-only diagnostic.
