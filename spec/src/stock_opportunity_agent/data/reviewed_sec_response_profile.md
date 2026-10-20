# Reviewed SEC filing HTTP response profile

`sec_filing_response_acceptance_v1` verifies a whole filing original from actual
retained HTTP receipts and unmodified SEC submissions payloads. It performs no
GET, source append, model execution, source time correction or research scoring.
No failed legacy proof automatically falls back into this explicit profile.

## Exact proof carriers

Each row has exactly one mandatory `sec_static_archive_body_response`, exactly
one root proof (`sec_submissions_root` or `sec_submissions_root_response`), and
at most one linked archive proof (`sec_submissions_linked_archive` or
`sec_submissions_linked_archive_response`). Missing, duplicate, competing or
additional kinds reject. Without archive, use the real root `filings.recent`;
with archive, use the real flat page selected by the real root `filings.files`.
Never repackage a flat page as a root/recent body.

All proofs retain `artifact: {path, sha256}`. For a managed root/archive carrier,
it names the actual managed envelope: exact SEC endpoint, `source_key=sec_edgar`,
`capability=filing_documents`, `payload_kind=json`, unique sanitized
`params=[["method","GET"]]`, and an aware retrieval instant.

A response carrier names the actual `results.json` receipt in `artifact`, and
also declares `entry_name`, `raw_response: {path, sha256}`, and exact `endpoint`.
The body proof additionally declares `expected_content_hash`. The supported
real receipt shape is shared by retained narrative-fetch-v2 and periodic
fetch-v1: top-level `requests`, `automatic_retries=0`, `redirects_followed=0`;
the selected request has `name`, `method`, `url`, `status`, `http_status`,
`response_url`, `started_at_utc`, `retrieved_at_utc`, `raw_response`,
`raw_sha256`, `bytes`, and `response_headers`.

Require one matching name and one request to that exact endpoint, GET, exact
HTTPS SEC URL without credentials/port/query/fragment, unchanged response URL,
`status=http_response_retained`, genuine integer HTTP200, genuine integer zero
retries/redirects, and aware start ≤ retrieval. Resolve the receipt's raw path
relative to the receipt directory if relative; require equality with the bound
raw path, receipt SHA, actual bytes/SHA and genuine integer byte count. Reuse
native `decode_response_text` with case-insensitive `Content-Encoding`, including
gzip/deflate; malformed compression/UTF-8 is a typed source rejection. Parse
root/archive decoded JSON directly; compare the whole decoded HTML string and
its content hash to the original. Do not normalize markup or silently redact it.

The root proof also declares `issuer_cik`, `accession_number`, `form`,
`primary_document`, `filing_date`, and `accepted_at`. Archive proofs declare
`filename`. For example:

```json
{
  "proof_profile": "sec_filing_response_acceptance_v1",
  "proofs": [
    {"kind":"sec_static_archive_body_response","artifact":{"path":"/results.json","sha256":"..."},
     "entry_name":"primary","raw_response":{"path":"/primary.raw","sha256":"..."},
     "endpoint":"https://www.sec.gov/Archives/edgar/data/1/000000000225000001/report.htm",
     "expected_content_hash":"..."},
    {"kind":"sec_submissions_root","artifact":{"path":"/managed-root.json","sha256":"..."},
     "issuer_cik":"0000000001","accession_number":"0000000002-25-000001","form":"10-Q",
     "primary_document":"report.htm","filing_date":"2025-05-05","accepted_at":"2025-05-05T20:00:00Z"},
    {"kind":"sec_submissions_linked_archive","artifact":{"path":"/managed-history.json","sha256":"..."},
     "filename":"CIK0000000001-submissions-001.json"}
  ]
}
```

## Identity, shape and availability

Root endpoint and strict CIK must agree with the canonical document company.
Source CIK accepts only positive integers or trimmed plain ASCII digit strings
of at most ten digits, not bool/float/sign/prefix extraction. A flat page gains
issuer authority from its exact unique safe filename link in that issuer root;
it does not acquire an invented CIK field. An accession submitter prefix may
differ from the issuer, as with KGC; never compare those prefixes as identity.

Require accession/filingDate/form/primaryDocument/acceptanceDateTime arrays, all
lists of equal length. Every other supplied parallel column must be a list of
that length. Require exactly one target accession; target identity fields must
be nonempty strings and match the root-proof declarations, with valid filing
date and aware accepted instant. A linked archive requires exactly one matching
root files entry, a safe basename, and exact `data.sec.gov/submissions/<filename>`
request. Its declared `filingCount` must be a genuine integer equal to page rows
(an explicit new-profile consistency condition, not a legacy gate). Require
valid ordered declared filing bounds and the target's actual `filingDate`
inside them. Whole-page date extrema need not equal the declared bounds; do not
introduce a tolerance or reinterpret acceptance time to force equality.

Require exact expected primary archive URL, canonical SEC document id, and the
shared [source-versus-form rule](filing_orientation.md). Preserve the verified
original's `filing`, `sec_filing` or `filing_body` alias; exact typed SEC sources
must agree with the actual parent form for both primary and exhibit profiles.
Generic aliases continue to support legitimate nonoperating forms and amendments;
other sources and substring aliases reject. Reconstruct the expected record
with that verified original source type and complete native filing metadata
(`provider`, CIK, accession, form and source URL). Complete record equality uses canonical
hashes, preserving JSON value types. The target accepted instant must exactly
equal row available, original available and published instants and be no later
than the actual case cutoff. Equivalent offsets preserve instants. Missing or
naive acceptance is unproven; no filing-date-midnight or Company Facts next-day
fallback is authorized. Retrieval times remain separate source facts.

This checks mechanical source qualification, not whether an official timestamp
is economically correct or a header/API conflict has been resolved. In
particular, a separately evidenced annual acceptance on Feb22 versus a filed
date of Feb21 is not silently converted to a different source time policy.
Body operating scope and information sufficiency require their own review.

## Explicit incorporated-exhibit profile

Primary body proofs declare `document_role=primary`. A qualified annual primary
can still be a wrapper and does not automatically qualify as full operating
narrative. The separate `sec_filing_exhibit_response_v1` reuses the mechanical
root/linked-target checks, but its body proof declares
`document_role=incorporated_exhibit`, `exhibit_document` and `exhibit_type`
(explicit null when unproved). It additionally requires exactly one
`sec_parent_primary_response` proof with the same response-carrier fields,
`document_role=primary`, and expected complete parent content hash. Root/archive
identity checks still refer to the real parent accession/form/primary.

Parse the actual whole parent HTML anchor hrefs and resolve them against the
proved parent URL. The exact requested exhibit must be a literal link to the
same issuer and accession directory with the declared safe exact filename.
Do not accept metadata relabeling or an unlinked URL. If an exhibit code such as
`99.1` or `99.2` is claimed, prove it from an independent exhibit-number cell
in the same index row containing that target anchor. Exactly one cell, at any
position in the row, must consist only of the complete code (optionally
prefixed by `Exhibit`), and the row must have one unique linked URL. Multiple
anchors to that same literal URL are compatible. Preserve superscript markup
provenance: only trailing `<sup>` annotations containing a complete ASCII
integer or parenthesized ASCII integer are numeric footnotes that may be
excluded from this code cell. Plain-text suffixes, nonnumeric superscripts,
superscripts embedded inside a code and description cross-references are not
exhibit-number proof. Conflicting target index rows, multiple code cells or
linked URLs keep the claimed type unproved; do not derive it from filename
order. Rows without a complete standalone code cell supply no code proof.
Absent index proof keeps `exhibit_type=null` rather than inventing its meaning.
This parser proves a source link/code, not AIF/MD&A/financial-statement semantics.

The exhibit is a separate original with id
`sec-exhibit:<canonical-company>:<accession-no-dashes>:<exact-filename>`. Preserve
`form` as the real parent form and add explicit `parent_form`,
`parent_primary_document`, `exhibit_document`, `document_role` and
`exhibit_type` metadata, alongside provider/CIK/accession/source URL. It never
overwrites the primary id or converts a 6-K parent into 40-F. Publication and
availability use the same proved parent acceptance policy; an older date
mentioned in the exhibit title does not backdate these exact bytes. Period,
units, body scope and sufficiency remain independently reviewed. Untaken or
unreviewed linked bodies remain unknown.

## Recovery and bounded verification

Reuse per-review immutable binding/decoded payload memoization, never a
cross-refresh cache. Materialize/open/refresh/worker reconstruction all recheck
the same originals, receipts, raw bytes, manifest membership and canonical
records. Unknown additions, marker/root changes and symlink escapes reject.
`DataSourceError` and malformed receipt/array input remain
`ReviewedSourceRejected`, never negative company observations.

Use isolated fixture tests for root and linked paths, managed/response carriers,
compression, equivalent offsets and issuer/submitter differences; rehash
receipt/URL/CIK/link/array/count/target/time/body/raw-path counterexamples while
retaining independent anchors. Include exact replay/restart/worker/drift and
the original profiles' safe regressions. Explicitly exclude the two legacy
LabelStore/fullprepare tests and guard real labels and `minimal.prepare` in the
final runner. No real case, global write or network is needed to verify code.
