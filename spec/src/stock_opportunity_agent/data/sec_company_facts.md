# SEC Company Facts normalization

Pure data normalization owns response-CIK validation and the existing typed
per-accession Company Facts product shared by acquisition and backfill. It
performs no network, store writes, model calls or research selection.

Each reported fact exposes a date-only `filed`, not a proved acceptance instant.
Its conservative policy availability is the next UTC midnight. Compare that aware instant
with the complete aware cutoff, including intraday times and equivalent offsets.
The same helper governs producer selection and deterministic Signal consumption
of both legacy nested and typed accession schemas. Reported period ends retain
their existing no-future-actual rule using the cutoff's UTC date; ordinary
forward-looking source prose is outside this fact-specific check.

Validate the response issuer against the requested CIK before constructing a
source product. Provider CIK accepts only a positive integer or a trimmed plain
1–10 digit string, never bool/float/prefix/sign/embedded text. Accession submitter
prefixes may differ from the issuer CIK. At deterministic consumption, both fact
schemas must match a canonical `cik_##########` document company and any declared
metadata CIK. Opaque company aliases require explicit metadata CIK; alias digits
are not an identity proof. Missing, malformed or conflicting identity raises the
existing technical validation failure, never a negative measurement or no-match.
This also applies to synthetic capability and measurement fixtures: their authors
must explicitly bind body CIK and document metadata CIK for an opaque alias.
Positive fixture construction does not authorize inference in the normalizer,
consumer or auditor. Missing or conflicting bindings remain negative validation
controls for both legacy nested and typed accession bodies; historical source
records and published Registry fixtures are not rewritten by a template repair.
Preserve standard taxonomy/tag/unit, original values, start/end, filed/form and
accession lineage. Historical products omit current `entityName`; the complete
provider response remains a separately timestamped proof document.

Use existing `sec-company-facts-document-v1` bodies. The pure normalizer has an
explicit `identity_policy`: `legacy_content_v1` preserves the existing `secfacts:`
accession/content identities and remains the compatibility default;
`raw-info-capture-v1` derives the complete record's capture ID after materializing
identical content, metadata and public times. These differ from old content-only aggregate IDs,
so append-only refetch cannot silently preserve an old unsafe availability
under the corrected identity. Old originals and completed runs remain unchanged;
new products require separate source qualification and an explicit reviewed view.

The shared normalizer accepts an explicit period/form/taxonomy/availability
selection and caller provenance. Backfill retains its frozen plan window,
metadata and complete output equality. Acquisition retains all supported
historical comparative periods (no new 550/1100-day fact cap); its upper reported
period boundary and availability are the actual cutoff. Request publication
lookback still belongs to resolver selection and does not truncate comparison
rows inside a selected accession. Acquisition records its exact selection and
policy hash rather than inventing a backfill plan.

New acquisition explicitly requests `raw-info-capture-v1` for typed products and
its retained whole-response document. Each new acquisition records its actual
materialization time once; a cached response is not a new HTTP request. Replaying
that recorded capture uses the same time/selection/provenance, without obtaining a
fresh clock. New selection, provenance or recorded time creates a new capture
version even when the selected facts are byte-identical. Existing raw proof
artifacts retain their old IDs and clocks. Source qualification explicitly
selects a legacy or capture recipe; changing the normalizer must never silently
change a frozen v1 reconstruction.
