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
Preserve standard taxonomy/tag/unit, original values, start/end, filed/form and
accession lineage. Historical products omit current `entityName`; the complete
provider response remains a separately timestamped proof document.

Use existing `sec-company-facts-document-v1` bodies and `secfacts:` accession/
content-version identities. These differ from old content-only aggregate IDs,
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
