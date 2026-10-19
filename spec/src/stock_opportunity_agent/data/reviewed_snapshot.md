# Reviewed historical source snapshot

Status: implementation contract for the trusted-input batch; source admission
requires actual proof verification and materialization. This is a narrow local view of reviewed
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

`materialize_reviewed_snapshot(review_path, root)` verifies every scoped original
and retained proof before writing the declared admitted canonical copies and an immutable manifest.
Its binding explicitly names `store_type=reviewed`, exact root and manifest hash.
`open_raw_info_store(root, reviewed_snapshot=binding)` requires that type, root
and hash even if the marker was removed or renamed; it cannot fall back to a
plain store. Production contracts retain this binding in
`limits.reviewed_source_snapshot`; coordinator and parallel workers use the same
loader. New minimal-round input manifests retain the binding, and preparation,
verification and runtime use that same view. Reviewed inputs with no explicit
binding are rejected. Existing plain-store contracts retain their old behavior.

The original proof reader supports the reviewed static SEC archive body plus
cached submissions acceptance pair. It checks exact endpoint/body equality,
issuer/accession/form/primary-document identity and exact accepted/available/
published instant equality. It never rewrites original availability to match
proof. Excluded and unknown records remain in the four-record review, outside
the materialized document set. Snapshot restart rechecks these same originals
and proofs; additions, missing files, changed scope/root/hash or content reject
before visibility. Snapshot returns the reviewed store type, never an appendable
plain in-memory copy. Enabled acquisition policy on this scope is rejected.
The cached submissions endpoint must be the exact SEC `data.sec.gov/submissions/CIK…json`
endpoint for the same issuer, in addition to its body identity. Materialization
resolves symlinks and rejects a destination within the original oracle root
before any mkdir or write, preserving that append-only oracle's file namespace.
Every scoped original record must physically belong to that declared oracle
root; relocating only its identity file cannot weaken the destination guard.

## Required checks

Reproduce the polluted news through the production normalizer and confirm the
old resolver admits it, then prove the new view excludes it at actual lookup,
Basic Info/Signal preparation, frozen input and runtime restore. Include actual
SEC forecast and same-unit shares positives, cutoff just before/at SEC
acceptance, unknown/missing proof, mismatched identity/content/hash, attempted
new adapter append/requery, snapshot/refresh/restart, global growth and original
bytes unchanged. Content semantics require independent original-material
review; no year/URL regex or substituted SEC prose cleans a provider summary.

## Market extension

The separately approved [market proof profile](reviewed_market_profile.md) adds
a narrowly supported Massive daily aggregate proof branch. It reuses the same
review/freeze/read-only view interfaces in a new five-record review and isolated
root; existing four-record SEC inputs and their historical bindings stay intact.
Source-family selection is explicit, never a fallback from failed SEC proof.
The five-original market cohort has materialization and negative-control
evidence; this does not admit other market records or close its known
consumer day-boundary/visibility gaps.

## Company Facts extension

The [Company Facts profile](reviewed_companyfacts_profile.md) explicitly supports
`sec_companyfacts_filed_next_utc_day_v1` for newly materialized typed accession
originals. It verifies a managed SEC cache, the retained whole-response proof and
a complete normalization record through the actual shared data normalizer. Old
aggregates and whole-response proofs never become admitted financial products.
Existing oracle-root, original-record and immutable view interfaces remain in
force. Within one review verification, repeated immutable bindings may share
their decoded bytes and one complete reconstruction; every refresh starts a new
verification and rereads/hash-checks all bound files. No process-wide or persisted
verification cache may bypass evidence drift.
