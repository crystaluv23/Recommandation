# Reviewed SEC Company Facts proof profile

`sec_companyfacts_filed_next_utc_day_v1` admits only newly appended
`sec_company_facts` originals with `sec-company-facts-document-v1` bodies. The
unchanged reviewed snapshot interface still requires each original under its
declared oracle root, full record/content hashes and an explicit disposition.
This profile neither admits old nested aggregates nor exposes the whole current
API response. All unknown/excluded rows and historical source views remain intact.

Each admitted row has exactly three proof kinds, each with the existing
`artifact: {path, sha256}` binding:

- `sec_companyfacts_cache`: exact managed SEC JSON cache envelope.
- `sec_companyfacts_raw_response`: retained original whole-response
  `RawInfoDocument`, used only as proof.
- `sec_companyfacts_normalization`: new complete normalization record.

The normalization record has this shape (hashes and products shown schematically):

```json
{
  "schema_version": "sec-companyfacts-normalization-v1",
  "normalizer_profile": "sec_companyfacts_filed_next_utc_day_v1",
  "source_cache": {"path": "/cache.json", "sha256": "..."},
  "raw_response": {"path": "/oracle/raw.json", "sha256": "..."},
  "item": {
    "cik": "0000000001", "company_id": "cik_0000000001", "symbol": "EXAMPLE",
    "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"
  },
  "selection": {
    "period_end_from": "0001-01-01", "period_end_through": "2025-07-31",
    "available_at_through": "2025-07-31T00:00:00+00:00",
    "taxonomy_allowlist": ["dei", "ifrs-full", "srt", "us-gaap"],
    "form_allowlist": ["10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A",
      "40-F", "40-F/A", "6-K", "6-K/A", "8-K", "8-K/A"]
  },
  "provenance": {
    "acquisition_policy_hash": "...",
    "acquisition_selection": "same selection object"
  },
  "normalized_at": "2026-10-20T00:00:00+00:00",
  "expected_products": [{"document_id": "secfacts:...", "content_hash": "...",
    "canonical_record_hash": "canonical_json_hash(complete document.to_dict())"}]
}
```

Require the normalization record's two source bindings to equal the row's cache
and raw-response bindings. Require the exact Company Facts endpoint for the
canonical padded CIK; cache `source_key=sec_edgar`,
`capability=financial_statements`, `payload_kind=json` and the unique sanitized
`params=[["method", "GET"]]` request. Use the shared strict provider CIK validator.
The whole response must canonically equal the retained raw document content,
whose source type, company, provider, CIK, content-derived id and retrieval clocks
must match. Bind aware cache and raw normalization instants without rewriting
either; new actual `normalized_at` must be no earlier than both.

Selection is the new acquisition product's full comparative-period selection:
lower period bound is `0001-01-01`, upper period bound is the UTC date of its
complete aware availability cutoff, and namespaces/forms equal the existing
standard lists. No new rolling historical cap is added. The selection cutoff
cannot exceed review scope; an admitted row cannot exceed the selection cutoff.
Provenance must be exactly the acquisition selection and its canonical policy
hash for `{"schema_version":"sec-company-facts-acquisition-v1","selection":...}`.

Reconstruct all products once through `materialize_company_fact_documents`,
with the record's exact item, selection, provenance and normalization instant.
Require unique expected ids and exact equality of the complete expected product
identity/hash set; no extra, missing or substituted product is allowed. Each
admitted original must equal its reconstructed complete `to_dict()`, including
metadata, taxonomy/tag/unit/value/period/accession, next-UTC-day availability and
retrospective/primary-audit flags. Its row availability must equal the original.
A review may explicitly admit a subset of those products; that does not assert
all materialized products were selected or read by a consumer.
Exact record comparison uses canonical complete-record hashes, including at
immutable replay and restore. Python's numeric equality must not equate JSON
`true` with `1`, or `1` with `1.0`, to bypass a bound original record hash.

SEC XBRL is the financial source authority. Retain
`retrospective_api_extraction=true` and `requires_primary_filing_audit=true` as
auditable limitations. Reconstruction does not assert a historical API vintage,
independent primary-filing value audit, complete narrative content, Signal
readiness or research benefit. No field is patched merely to obtain admission.
Malformed provider input, including `DataSourceError`, is a
`ReviewedSourceRejected` boundary failure, never a negative company observation.

Within a single `_verified_review`, memoize bound-file reads/decodes by resolved
path plus declared SHA, and complete normalization by its three immutable source
bindings. Never reuse a result across refresh/restart. Every refresh rechecks
all file bytes/hashes and complete membership, retaining existing SEC and market
behavior and the original-oracle destination guard.

Focused tests cover full materialize/open/refresh/worker recovery and per-call
reuse, exact cutoff/equivalent offsets, issuer/request/body/record/clock changes,
unit/value/period/filed or premature availability, missing/extra expected ids,
whole raw rejection, and changed proof/manifest/files at refresh. Use isolated
fixtures and temporary oracles only; no network, labels or actual source append.
