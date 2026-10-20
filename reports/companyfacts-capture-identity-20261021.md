# Company Facts capture-version identity: local implementation

The user approved capture-version IDs for repeated acquisitions whose bodies and
public timestamps agree but complete acquisition metadata differ. This checkpoint
implements that policy; it does not establish actual GPRE source admission.

New acquisitions and Company Facts backfill v2 explicitly use `rawcap:v1:` IDs
derived from the complete typed canonical record except its ID. Creation,
serialized restore, append, load, search and document enumeration validate that
identity. Exact recorded replay is idempotent. Strict JSON keeps boolean, integer,
float, null and absent metadata distinct. Legacy normalizer callers, backfill v1
and the original reviewed-source profile retain their original recipes and IDs.
The new capture proof profile reconstructs its complete expected product set.
Identical-content deduplication remains a consumer operation, so capture versions
do not count as independent facts.

## Evidence

- [Safe verification summary](../runs/diagnostics/companyfacts_capture_identity_20261021_v1/safe-summary.json):
  33 tests passed in 7.400 seconds, including capture identity, original reviewed
  profile, fake-transport backfill, and eight retained-source PIT controls.
  Socket, LabelStore, full prepare and non-temporary store tripwires all remained
  zero. The summary binds all twelve implementation/spec/test files and retains
  original candidate failures and source copies.
- [Independent core counterexamples](../runs/diagnostics/companyfacts_capture_identity_boundary_20261021_v1/core-results.json):
  typed metadata variants, forged IDs and disk records reject; legacy refetch and
  two captures resolving to one fact remain valid. An intermediate implementation
  rejected nested metadata drift at load but leaked it through search/enumeration
  into the resolver. The current implementation rejects all those exits. The
  earlier intermediate source was reconstructed, not captured contemporaneously.
- Root separately ran the existing canonical-CIK acquisition, legacy same-content
  replay and source-copy deduplication tests: all three passed, zero network
  attempts. Existing PIT tests changed only their recorded test clock and the
  expected identity recipe; source values, periods and public-time oracles remain.
- [Subsequent independent actual57 review](../runs/diagnostics/companyfacts_capture_identity_boundary_20261021_v1/profile-independent-review.json)
  reconstructs all 57 retained products exactly under the legacy recipe and
  confirms capture changes only IDs. A temporary four-product native view passes
  snapshot/reopen/replay; reducing the expected set to four or mixing recipes
  rejects. The old raw proof and four conflicting global records remain unchanged.
  Its first temporary-oracle setup error is retained as a review harness failure.

## Remaining acceptance

No real GPRE record was appended, reviewed view created, or model called by this
checkpoint. Four hash-bound actual collision pairs were exercised only in a
temporary store. A separate source-only phase must reconstruct all 57 products,
retain the 53 already qualified records, qualify and append only four new capture
versions, preserve every old record, and verify latest-Q1 selection and exact
consumer inputs. It must use saved proofs with zero new GET, LLM, labels or Signal
execution, and must not reenter completed stages.

F7 temporal-facet loss remains failed at its original frozen 0/1 denominator.
Capture identity repair does not address that failure or close the Fast/Slow MVP.
