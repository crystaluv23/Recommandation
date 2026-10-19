# Reviewed historical source snapshot

Status: proposed implementation for the next trusted-input batch; no source
admission is asserted by this file. This is a narrow local view of reviewed
documents, not a rewrite of RawInfoDocument or the global oracle.

## Review and immutable view

A hash-bound manifest declares its exact company/time/document scope and one
`admitted`, `excluded` or `unknown` disposition per scoped original document,
with document id, full original-record hash and content hash. Each admitted
record requires locally retained original-source evidence and a reason covering
issuer identity, period/unit/content scope and content availability. URL/hash
membership alone does not establish semantics. For the first narrow cohort,
two Bumble SEC originals may be reviewed against byte-identical static archive
body caches and exact accession acceptance timestamps from cached SEC
submissions; the polluted provider-news original is excluded. Unknown records
stay unknown, never nonexistent. Transcript complete-content proofs remain
pending and are not admitted by a conference-start announcement.

The runtime opens an actual isolated read-only Raw Info snapshot containing
only admitted canonical records, bound to this manifest. It cannot expose the
global oracle through `.documents`, exact `load`, `search`, `snapshot` or
`refresh`; attempted unknown/unreviewed appends must fail before visibility.
Exact admitted replay is idempotent. Original records and evidence remain in
place, and the snapshot manifest explicitly records exclusions. Resolver lookup
and requery use this same store. Acquisition is disabled for this frozen local
scope; a mistaken/fake adapter return cannot bypass admission or silently open
the whole oracle. Missing reviewed coverage yields a DataGap, not negative
company evidence. This first view cannot support whole-cohort readiness or
claim the global oracle is clean.

## Freeze and recovery

The source-review manifest, original record hashes, local evidence hashes and
admitted store identity are bound into new input freeze. Runtime reconstruction
loads only that view, verifies the same evidence and refuses drift/missing
proof, changed admission, extra documents or a widened source root. Refresh
and restart retain the manifest's original scope. Old completed inputs remain
unchanged; no old run is resumed with new admission semantics. Global oracle
growth alone cannot make a new record visible in the frozen view.

## Required checks

Reproduce the polluted news through the production normalizer and confirm the
old resolver admits it, then prove the new view excludes it at actual lookup,
Basic Info/Signal preparation, frozen input and runtime restore. Include actual
SEC forecast and same-unit shares positives, cutoff just before/at SEC
acceptance, unknown/missing proof, mismatched identity/content/hash, attempted
new adapter append/requery, snapshot/refresh/restart, global growth and original
bytes unchanged. Content semantics require independent original-material
review; no year/URL regex or substituted SEC prose cleans a provider summary.
