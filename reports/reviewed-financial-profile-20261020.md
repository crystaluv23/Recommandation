# Reviewed SEC financial profile

2026-10-20. The explicit
[Company Facts profile](../spec/src/stock_opportunity_agent/data/reviewed_companyfacts_profile.md)
qualifies new typed accession products against three retained proofs: the exact
managed SEC cache, the old whole-response proof record and a complete new
normalization record. It uses the existing materializer, oracle-root guard and
read-only view interfaces. It cannot admit legacy aggregates or whole current
responses as historical financial input.

The reader verifies issuer, endpoint/request, source and normalization clocks,
standard selection, acquisition policy, complete reconstructed product membership
and each original's full canonical record. The existing filed-next-UTC-day
policy remains; no exact acceptance time or historical API vintage is inferred.
SEC CompanyFacts is an existing financial authority. Retrospective extraction
and primary-filing-audit limitations remain true in metadata; this profile does
not claim a completed primary-filing value audit.

Independent adversarial review first found that Python equality accepted
metadata true-to1 and integer-to-float substitutions despite different canonical
record hashes. The initial failures and original reader are retained. Canonical
full-record comparison now covers financial originals, read-only append and
materialized restart. Numeric equivalence cannot satisfy an exact JSON record
contract. RawInfoStore's existing append-only refetch policy is unchanged.
The diagnostic's append/load and worker/restore checks use the same canonical
criterion; four real temporary-store replay controls pass.

The [final focused run](../runs/diagnostics/financial_profile_boundary_20261020_v1/sec-companyfacts-profile-final-related-selectors-v2.json)
passes30 explicit safe tests, with unreadable LabelStore and forbidden prepare
tripwires. It includes9 new financial tests,11 existing market tests and10 scoped
SEC tests. The [independent counterreview](../runs/diagnostics/financial_profile_boundary_20261020_v1/final-results.json)
rejects both original type substitutions, nonexact append and a rehashed modified
view at restart. Its real FTAI-cache probe uses synthetic raw-proof wrappers and
temporary products explicitly; it is not actual original-source admission.

Root's earlier31-test whole-module selection repeated a known scope mistake:
two old tests hashed real label files and attempted a temporary full preparation
that was rejected. No research cycle or model ran. That
[exception](../runs/diagnostics/financial_profile_boundary_20261020_v1/root-related-tests.json)
is retained and cannot support a no-label/fullprepare claim. Final safe selectors
exclude both tests and install tripwires. A separate runner setup error before
zero tests is also distinguished from production behavior.

The [new diagnostic](../scripts/diagnose_reviewed_anchor_financial_snapshot.py)
separates preparation from execution, binds code/spec/source inputs and validates
all candidate groups through the actual profile before any global append. It
then requires exact native append/load, unchanged old bytes, an explicit new-file
inventory, a separate reviewed view and all270 exact v12 input preparations.
This checkpoint has not executed those operations on the fixed15 actual cases.
No new GET or production LLM completion occurred. Source qualification/readiness,
full48 preparation, model behavior, Fast/Slow and the MVP remain open.
