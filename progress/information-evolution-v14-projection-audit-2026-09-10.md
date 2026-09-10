# V14 source projection and learning-boundary audit

V14 was safely interrupted during case 14 with 13 complete cases, no committed
Fast round or Slow cycle, 236 completed responses, two failed attempts and one
interrupted attempt. Recorded model cost is $0.575365; interrupted usage is not
known. The frozen workspace remains immutable evidence under code `9da679f`.

## Confirmed information loss

Case `cik_0000895728:20250930`, Signal `financing_listing_action:v1`, returned
domain-unavailable because its visible projections contained general disclosures
rather than completed financing actions. Its actual resolved documents included
`sec:cik_0000895728:000110465925061164`, an as-of-eligible filing describing a
completed June 20, 2025 senior-note offering. The original request
`0e62b6db7eb96081ac044ecbf6368cfc4324cd63ccb6c9e66a85a6f0c3351484`
omitted that document from its 32,000-character projection. The source was present
and retrieved; loss occurred before the model received the source.

The shared projector ranked chunks using all extraction-skill prose, then filled
one global budget. Common disclosure language could dominate, and its nominal
document-diversity sort evaluated an empty set before selection. The repair ranks
each Signal's eligible chunks using version-owned retrieval/evidence terms,
alternates Signal queues, and dynamically prefers unseen documents. It preserves
the character budget, normalized-to-raw offsets, eligible citation ids and
point-in-time rules. It contains no company, model, or financing-event exception.

Exact input replay now includes the issuance passage within 31,678 characters.
This proves restored visibility, not the correctness of a fresh model judgment;
the latter remains a live successor check. Bounded projection still cannot prove
source absence, and this repair does not guarantee every relevant span fits.

## Other checked boundaries

- All 13 completed Predictor and post-hoc contexts match persisted requests.
  Persisted request body hashes and byte counts match.
- All 24 frozen cases were replayed against nine deterministic Signals using
  normal retrieval: 216 comparisons, 28 unavailable. Re-execution of each
  unavailable Signal over all local as-of-eligible company documents recovered
  zero results. Missing supported fields, comparable periods and freshness remain
  explicit; using the same parser cannot independently prove parser completeness.
- Runtime technical statuses are excluded by
  `_signal_learning_events_from_record`. Domain-unavailable is separately counted
  as with/without-input coverage; it is not directional error. This does not
  protect against a wrongly classified source absence, as the projection example
  demonstrates. Slow must verify source facts before changing a Signal.
- Real malformed JSON at attempt 219 entered bounded structured correction and
  execution continued. Failed attempts retain their paid usage and original
  responses. No fabricated evidence or successful-cycle pointer was introduced.
- Case-local `H_reflect` updates ResearchState. Post-outcome case reflection,
  vertical Plan critique and horizontal round reflection feed committed meta.
  Slow H1 receives the masked meta view and fingerprints that exact view.
  V14 has not yet reached this downstream live boundary.

## Verification and remaining acceptance

All 643 tests pass, including a regression with a long competing filing, a short
action disclosure, independent peer-Signal evidence, source/input permutations,
changed skill prose, bounded length and literal source mapping. Ninety focused
Fast/Slow/reliability tests also passed before this repair. V15 must demonstrate
actual Fast/Slow completion and actual reflection uptake; promotion, next-Fast
use and predictive benefit remain separate observations.
