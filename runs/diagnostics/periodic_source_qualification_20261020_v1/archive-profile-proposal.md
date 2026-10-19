# Root-linked SEC submissions archive proof proposal

Status: proposal only, awaiting root decision. No production source/spec change,
GET, source append, source admission, model, Signal, labels or full preparation.
The fixed inventory (`5888ce3b…d39aa1`), proposal (`5553b9ea…ffc456`) and
annual-pointer (`4d4c772e…05cee3`) remain unchanged. This document supersedes any
reading of the earlier proposal that would make whole-page date-extrema equality
an admission gate; the earlier artifact itself is preserved.

## Current implementation and evidence

- `src/stock_opportunity_agent/data/reviewed_snapshot.py:63`,
  `_verify_sec_document`, accepts exactly static archive body plus root
  submissions acceptance proof. It reads `body.filings.recent`; the dispatcher
  at lines 360–362 selects `sec_archive_acceptance_v1`. A flat history page
  cannot currently qualify, and must not be repackaged as the root response.
- `SecEdgarClient.historical_submissions` fetches an exact validated basename
  under `https://data.sec.gov/submissions/`. Its shared `_filings_from_arrays`
  (sec_edgar.py:162) parses recent and flat historical arrays identically.
  Required accession/filingDate/form/primaryDocument arrays must be lists of
  equal length. Optional array access uses `array_get`; malformed/missing
  acceptance becomes `None`, while an aware upstream instant is retained.
- `SecFilingAdapter.acquire` follows at most three root-declared pages selected
  by declared filing-range overlap, newest first. It deduplicates by accession,
  fetches the primary body, and uses aware acceptance if present; otherwise the
  adapter's existing fallback is filing-date midnight. This source qualification
  proposal requires proved aware acceptance, as the existing reviewed filing
  profile does, and does not authorize fallback or invent another time policy.
- The fixed inventory binds seven implementation files and all actual inputs.
  A real client plus adapter, served the unchanged retained root, linked flat
  archive and body at their exact endpoints by a closed local transport,
  reconstructed the entire old MS 8-K record, including `11:59:47Z`, exactly.
  This establishes a retained matching official cache chain. It does not
  identify the August writer or prove a newer API clock incorrect.

The current reviewed root validator locates a unique target but does not perform
the client's complete parallel-array type/length checks. Its source-boundary
fixtures cover duplicate proof kinds, changed issuer endpoint and missing
acceptance array elements. The new branch should explicitly validate its own
shape and unique target; it must not silently generalize the old branch, treat
client deduplication as proof uniqueness, or claim the old validator was strict
on every malformed-array variant.

## Explicit new profile and retained artifacts

Propose `proof_profile=sec_linked_archive_acceptance_v1`, with an independent
dispatcher branch and no fallback from failed root-only proof. Preserve all
existing row fields, original-oracle root guard, canonical complete record hash,
cutoff and read-only materialization/recovery interfaces.

The minimally supported cache form has exactly three proof kinds:

1. `sec_submissions_root`: a bound managed root cache for
   `https://data.sec.gov/submissions/CIK<issuer-cik-10>.json`.
2. `sec_submissions_linked_archive`: a bound managed flat history cache, plus
   the exact `filename` selected from that root's `filings.files`.
3. `sec_static_archive_body`: the existing exact static-body cache binding,
   endpoint and expected content hash.

The archive proof declares issuer, accession, form, primary document and the
proved aware acceptance instant, using the same meanings as the existing
acceptance proof. Bind the root and archive separately; neither is synthesized.
Require managed request source `sec_edgar`, capability `filing_documents`,
expected payload kind, exact endpoint and unique sanitized `GET` request.
Preserve retrieval instants as retrieval facts; do not use them to backdate the
filing or assert a cutoff-time API vintage.

For a newly retained GET receipt rather than an existing managed text cache,
choose an explicit body representation before implementation: a bound successful
request record plus its separately hash-bound raw response bytes. Verify exact
GET endpoint, empty query, successful HTTP status, receipt/raw membership,
retrieval instant and response SHA, then use the real SEC transport decoding
semantics and require the resulting whole string to equal the original content.
The concrete collector receipt fields must be frozen with the real collected
artifact; a receipt JSON object must not merely be assumed to be a managed cache.
An implementation may expose a distinct receipt proof kind, with an exact
three-kind set selected explicitly, rather than trying representations on
failure. Prefer retaining the existing managed cache form when the actual
collector already provides it. Neither carrier authorizes body trimming or
fabricated root/recent wrappers.

## Mechanical checks, with their contract basis

| Check | Existing support and proposed handling |
|---|---|
| Root issuer | Existing reviewed source contract binds root endpoint/CIK and canonical document company. Require strict positive integer/plain digit CIK normalization; never bool/float/prefix extraction. Flat pages have no intrinsic issuer CIK, so their authority comes from the exact issuer root link. |
| Unique root link | Native acquisition follows manifest-declared safe filenames. New proof explicitly requires exactly one `filings.files` entry matching the archive filename; reject missing/duplicate links, unsafe basename, other endpoint or changed root issuer. |
| Page arrays | Native client requires four list arrays and equal lengths. New proof additionally requires a complete acceptance list of the same length because accepted time is mandatory for reviewed admission; any supplied parallel-array column must be a list of that count. Validate target identity/date/time fields as correctly typed values, not coercible bool/numeric substitutes. |
| Unique target | Current reviewed root proof requires one accession match; native acquisition deduplicates. New proof also requires exactly one exact target in the linked page, with exact form/primary/accepted values. Duplicate target remains ambiguous even if the duplicates agree. |
| Page count | Native client/adapter does not use `filingCount` as a gate. The retained three pages all match their root counts. Proposed additional source-binding consistency check: if the root declares a count, require a genuine nonnegative integer matching array length. Label this as new profile proof validation, not a previously enforced time rule; root approval is required before implementation. |
| Declared date window | Native adapter uses root `filingFrom`/`filingTo` as page-selection ranges. For this explicit target proof, where valid declared bounds apply, require the target's `filingDate` in that window. Use the SEC filing-date field, not the UTC date of acceptance; after-hours/weekend acceptance and filing date can differ. |
| Whole-page extrema | Neither current source spec nor native client requires declared bounds to equal all page filing-date extrema. Record differences; do not reject every otherwise valid target, add a one-day tolerance, guess a timezone or rewrite clocks. |
| Target PIT | Existing reviewed filing contract requires exact aware accepted instant equal to review-row available, original available and published instants, and no later than the actual case cutoff. Preserve this rule directly; no financial filed-plus-one-day policy is applied to a filing. Missing/naive acceptance stays unproven. |
| Body/original | Require the exact expected SEC archive URL, byte-bound retained body/receipt, full original content/hash, company/id/form/accession/source metadata and canonical complete original equality. Use the actual client/filing adapter with the retained payloads for reconstruction, without editing input arrays or copying discrepant fields from the original. |

All target identity fields must agree with the bound root issuer and original.
An accession's first ten digits identify a submitter and need not equal the
issuer: KGC issuer `0000701818`, accession `0001104659-25-028819`, is a required
positive. The archive URL uses issuer `701818` and the complete accession path.
Do not infer flat-page issuer identity by stripping digits from an alias or by
matching accession prefix. The primary filename must be the exact declared SEC
primary, with an exact safe archive path and no query/host substitution.

The retained MS pages illustrate the date distinction: count/array/name checks
agree, but root `filingTo` versus observed page maximum is Sep09/Sep10 for page
001, Jul29/Jul30 for 002, and May31/May30 for 003. MS Q1's actual May05 filing
is inside its declared Apr21–May31 page-003 window. Its exact aware acceptance
is `2025-05-05T20:13:06Z`, before the Jul31 cutoff. Page-001 MS Q2 acceptance
`2025-08-04T20:30:56Z` is after that cutoff and cannot replace Q1. KGC's annual
40-F is already in root `recent` and should continue through the original
profile; the new archive branch is not required for it.

## Bounded implementation and tests after root approval

Add a single explicit linked-archive verifier beside `_verify_sec_document` and
a dispatcher case; retain the old root profile and its fixtures. Reuse existing
bound-file decoding and per-review memoization, with fresh checks at every
refresh/restart. Avoid cross-refresh cache, new canonical schema, production
adapter edits, source writes, marker changes or a general proof framework.
If body receipt support is needed, freeze its real carrier shape first and add
only the small explicit byte/receipt reader needed for that carrier.

Focused isolated controls should include:

- One positive linked flat page, with issuer/submitter prefixes different, a
  whole-page extrema discrepancy outside the target, and a target safely inside
  its declared window. Run materialize → open → refresh → worker snapshot;
  require canonical originals/membership to survive exact restore.
- The original root/recent path remains a positive with its existing proof set;
  failed root proof cannot auto-route through the linked profile.
- Rehash a same-filename archive cache while changing its endpoint/target
  identity/form/primary/accepted value, or substitute an archive from another
  issuer root. Retain the original static body and root binding as independent
  anchors. Reject inconsistent proof even if outer hashes have been refreshed.
- Missing/duplicate root link, duplicate target, malformed unequal/scalar
  arrays, invalid target date/acceptance, mismatching declared count, target
  outside its declared window, changed body/hash/metadata, premature original
  available time and accepted-after-cutoff all reject as source failures.
- Equivalent aware offsets preserve instants; naive timestamps remain unknown.
  JSON `true`/`1` and integer/float differences cannot bypass full-record
  equality during admission, replay or rehashed materialized-copy recovery.
- Changed proof/manifest/original after materialization rejects on refresh and
  worker reconstruction; root relocation/symlink escape, global growth and
  attempted unknown append cannot widen the reviewed view.

Do not claim an unsigned reader can distinguish an entirely self-consistent
forgery of all retained sources from genuine official bytes. Rehashed
counterexamples must keep at least one real independent bound source as anchor.
Mechanical proof also does not establish that a 6-K/8-K primary contains full
operating narrative. Preserve existing covers/clock-conflict dispositions,
semantic review, fixed case cutoffs and annual-pointer unknowns.
