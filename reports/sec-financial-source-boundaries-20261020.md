# SEC financial source boundaries

2026-10-20. The fixed15-case [inventory](../runs/diagnostics/financial_source_qualification_20261020_v1/inventory.json)
binds15 old financial aggregates,15 whole-response proof documents and15 exact
SEC Company Facts caches. At the original normalization clock, the old native
adapter reconstructs all30 complete document dictionaries. That equality proves
provenance wiring, not eligibility: the FTAI July31 midnight aggregate contains
364 facts filed onJuly31, before their conservative next-UTC-day availability.
The old adapter also constructs a requested MS identity from an ENB response.

The shared [normalizer](../src/stock_opportunity_agent/data/sec_company_facts.py)
now validates the response CIK before construction and emits existing typed
per-accession products. The existing date-only filed policy is applied using the
full aware cutoff: same-day rows are excluded, exact next midnight admits them,
and equivalent offsets agree. Tag/unit/value/start/end/form/accession are kept;
all comparative periods remain eligible without an arbitrary1100-day cap.
The whole response stays separately timestamped proof, outside historical
model input. Acquisition and modern backfill share the pure helper; the latter's
frozen selection,12 complete FTAI products,3380 selected rows and statistics are
[identical to the prior implementation](../runs/diagnostics/financial_source_qualification_20261020_v1/producer-backfill-final-equivalence.json).

A real append/restart probe confirms that changing only an old same-ID record's
time is swallowed as idempotent replay. The new accession/content identities
therefore coexist with old originals, rather than pretending to correct them.
No original or completed snapshot is rewritten. Neither source reconstruction
nor this repair admits the old aggregates into the reviewed view.

Independent review then found that a persisted legacy foreign-issuer body could
still reach the deterministic consumer. Its initial19527-fact counterexample is
retained. Both recognized SEC schemas now verify body CIK against document
company and any declared metadata CIK. Canonical company identities or explicit
metadata are required; opaque aliases are not inferred from digits. Malformed,
missing or conflicting identities produce the existing technical validation
failure. The [final counterreview](../runs/diagnostics/financial_source_qualification_20261020_v1/independent/producer-consumer-review.json)
persists and restores that legacy input, then confirms the actual exact-net-share
executor persists validation_failed/unavailable with the issuer reason. It is
not a negative measurement or evidence that the Signal is absent.

Root ran all four relevant modules with sockets forbidden: **98 tests passed**
(90 producer/backfill/financial tests plus8 independent date,offset,issuer and
real-store replay controls). The [raw final log](../runs/diagnostics/financial_source_qualification_20261020_v1/root-final-98.log)
and original-implementation failures remain separate. An initial independent
fixture error is retained and not counted as a production failure. Final source
bindings match both the original root run and independent review. A subsequent
EOF-only formatting cleanup passed the same98 tests; its separate
[root verification](../runs/diagnostics/financial_source_qualification_20261020_v1/root-format-verification.json)
retains the new bindings and an initial verification-bootstrap import error. No new production LLM
completion, external LLM API, GET, real LabelStore access or full preparation was
performed. One local deterministic invalid-source execution verifies the failure
path only. Host-agent tokens/cost remain unmeasured.

The adjacent legacy FeatureRecord adapter is explicitly date-level and is not
in the current nine-Signal RawInfo consumer chain. Its date-inclusion behavior
receives no intraday PIT qualification from this repair; its semantics are not
silently redefined. Next-UTC-day is a policy instant, not a proved exact SEC
acceptance time. Current taxonomy descriptions and retrospective extraction also
require their own source review before historical model exposure.

This closes the tested local producer/consumer defect family. It does not close
financial source authenticity, all15 sources, nine-Signal readiness or the MVP.
Next: define a financial-specific proof contract, create only individually
qualified new typed products in a separate reviewed view, and measure the same
exact Registry requests with all unresolved outcomes retained. Do not reuse the
SEC filing or market profile as financial proof or rerun a full successor while
source prerequisites fail.
