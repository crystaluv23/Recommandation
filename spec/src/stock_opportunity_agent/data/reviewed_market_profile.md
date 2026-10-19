# Reviewed Massive daily-market proof profile

Status: implemented and independently checked in the five-original narrow
source cohort; each new record still requires this proof verification. The completed
SEC view and frozen H_init batch remain unchanged. This extends the existing
reviewed snapshot reader with one independent market proof profile; it does not
change RawInfoDocument, global oracle metadata or the generic store interface.
No additional data or external LLM request is required.

The next review has the existing four records unchanged plus the exact original
BMBL market record (five-record denominator). Its new materialized root exposes
only the two admitted SEC records and, if every check below succeeds, that
original market record. Polluted news remains excluded and transcript unknown.
The old four-record manifest/root are not overwritten. Admission and refresh
use the same proof helper; load/search/snapshot/acquisition isolation and
explicit freeze/root/manifest binding retain their existing behavior.

## Required local proof checks

1. Bind the original complete RawInfoDocument and old provider cache by bytes.
   Require market_data source type and the reviewed company, symbol, source
   provider, aware availability/publication and original per-bar retrieval metadata and exact date
   bounds. The old endpoint must be the expected Massive one-day aggregate path
   with that symbol/start/end, its sanitized request must be GET,
   adjusted=true, ascending, with the declared limit, and response must identify
   the same symbol, adjusted basis, successful complete page and daily data.
2. Reuse the actual production provider parser and HistoricalPriceAdapter with
   the original retrieval instant and original source inputs. Require complete
   reconstructed `to_dict()` equality, including full content/hash, identity,
   times, all prices and metadata. The HTTP cache retrieval clock and later
   normalization clock are separate runtime facts: bind both, require every
   canonical bar to use the same aware normalization instant no earlier than
   the cache instant, and pass that declared normalization clock to the original
   parser. Equivalent timezone offsets denote the same instant. No arbitrary
   clock tolerance is introduced. Do not replace mismatching fields with values
   copied from the original merely to obtain equality. Every original daily
   observation must be valid, chronological, unique and within declared request
   and cutoff bounds; metadata.prices and body must agree through the existing
   normalizer. No trimming or rewriting of the canonical record is allowed.
3. Bind the retained read-only historical ticker response and its exact request
   record. Verify HTTP/provider success, expected endpoint/date, symbol, CIK,
   common-stock/exchange/currency identity, and no unprocessed page. Its request
   date is the original series' latest observation date. This is the retained
   historical issuer proof, not a current metadata.symbol assertion.
4. Bind the retained all-type split request and raw response. Verify the exact
   expected endpoint and symbol; coverage must begin at the prediction cutoff
   UTC date and extend through the later of the original aware cache and
   normalization retrieval UTC dates. An event-type
   filter or shorter interval is insufficient. Require HTTP/provider success,
   zero returned events and no next page. Known pagination aliases may be
   absent or explicitly null only; false, zero, empty string/array/object are
   malformed shapes, not proof of a complete page. Its retained retrieval instant must
   be no earlier than the end instant it purports to cover; a query made before
   the old fetch cannot prove absence through that later fetch. This narrow profile cannot admit a
   nonempty ledger by inventing adjustment factors; such inputs remain
   unsupported/pending and are not negative company observations.
5. The retained 235-row unadjusted response is additional corroboration. If
   included, bind its exact request/raw bytes, adjusted=false and all overlapping
   OHLCV values. Fifteen old rows not returned a second time are not thereby
   invalid; duplicate download of every historical bar and cutoff-time archived
   vendor vintage are not new admission requirements. The complete original
   250-row production reconstruction and bounded split-basis proof are the
   primary checks under the existing historical-backfill contract.

Proofs use hash-bound existing local artifacts, exact request identities and
source shapes. They do not authenticate arbitrary proof authors or establish a
new signature/trust system. Unknown/failed proof remains typed source-boundary
rejection. No provider or canonical times are corrected to fit the review.

## Frozen mechanical acceptance

Freeze the five originals, old raw cache, three retained GET request/response
records, new review and new view identity before actual consumption. Reuse the
production loader, worker snapshot, resolver, Basic Info collection and
`_prediction_baseline_from_market_documents`; compute its real output rather
than inserting a hand-calculated price. Require the original document's complete
prices and a usable fixed runtime baseline, preserving the reported raw source
and computation lineage. This does not close Predictor behavior or whole-case
readiness: the full Registry/cohort requirements still apply.

Reject wrong issuer/symbol/date, old-cache endpoint or sanitized parameters,
changed adjusted flag, duplicate/out-of-bound/late bars, inconsistent normalized
prices/content or aware clocks, missing/truncated/paginated split coverage,
nonempty ledger, changed raw proof/record, widened review scope and explicit
binding/root/manifest deletion or downgrade. Test changed-but-rehashed local
proof copies as shape/identity counterexamples, not merely checksum drift.
Retain the old SEC positives, exclusions, unknown gaps and source originals.
No role answer is needed for these deterministic qualification checks; later
Predictor or other production model nodes require a fresh isolated role batch.
