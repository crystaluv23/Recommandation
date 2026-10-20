# Current financial execution and bounded reading diagnosis

2026-10-21. Engineering MVP remains open. This batch adds actual deterministic
measurement evidence on the reviewed GPRE source view; it does not execute an
LLM Signal or establish Slow discovery, feedback consumption or new-version reuse.

## Frozen scope and actual execution

The exact current comparison is the existing v12 snapshot with18 refs, hash
`40a451c051b0bfbdf424121a5362405f2fae6672c2be7b0f51e8072e8bd4ae8d`.
Nine financial refs use their existing deterministic implementations. This does
not replace the historical v6 freeze or its three LLM financial versions.
The case is GPRE/CIK0001309402 at2025-05-30UTC, using the completed1780-document
reviewed source view. No outcome labels were read.

Before execution, an independent source-only oracle froze nine expectations:
seven uniquely defined outcomes and two explicit period-policy unknowns. It
retained504 complete facts from23 source files and primary-filing corroboration;
it did not call the Signal functions. Root separately recomputed the seven
unique quantities with exact fractions and checked their complete source rows.

The sole native executor froze4136 source/oracle/definition bindings and253
code bindings at `6b7205ec15785851da9c0009dcda124eec9f498a`. Prepare first rejected
a diagnostic wrapper-shape mismatch before any stage directory or execution
marker; the corrected preflight compares five exact snapshot identity fields
and43 definition-file bindings separately. One subsequent prepare succeeded.
The fixed plan hash is
`8e8e406273d1f9805156e08d2f1155bf7da7044ddacc552d92c48da19239419a`.

One actual native batch completed in20.261seconds, returning nine raw results.
Every result was saved before comparison. Model calls, GETs, labels and append
operations were zero. Native `signal_calls=9` counts results, not independently
instrumented individual callable invocations. Exit0 denotes runner completion;
the saved acceptance status is **completed_acceptance_failed**.

| Signal | Raw measurement | Frozen verdict |
| --- | --- | --- |
| cash_burn_rate_elevated:v2 | 0.5581685427441436 ratio, positive | Pass |
| cash_reserves:v2 | 98610000 USD, neutral | Pass |
| cash_to_current_liabilities_ratio:v2 | 0.3027307473866794 ratio, negative | Pass |
| gross_margin_change:v3 | -0.11352199389831603 fraction_difference, negative | Record only: comparison-period policy ambiguous |
| liquidity_runway_months:v3 | 5.374720662778656 months, positive | Pass |
| net_share_retirement_yoy:v3 | -0.011493345542381794 fraction, neutral | Pass |
| operating_cash_flow_margin:v2 | -0.09150395251988729 fraction, negative | Pass |
| revenue_acceleration:v2 | 0.26114966938450923 fraction_difference, positive | Record only: earlier-growth-pair policy ambiguous |
| revenue_growth_yoy:v3 | 0.007201773568603631 fraction, neutral | Fail: prior whole-row alternative absent from frozen allowlist |

The fixed denominator remains9: **6 strict passes,1 strict failure,2 unknowns**.
All seven uniquely specified measurements match the frozen numeric, state,
unit and current-period expectations. That narrower fact does not convert the
batch to7/7 or9/9 acceptance.

## Independent source and consumer audit

The independent audit rehashed all4389 bindings and checked the actual request,
selected document IDs/hashes/availability/order and final source fingerprints
for every result against the earlier input-only v12 selection. All nine match.
It checked21 complete source evidence rows and nine persisted consumer
projections; measurement, execution, state and evidence remain faithful.
These are public model-facing projections, not fresh model consumption.

The strict revenue-growth failure is an oracle inventory limitation. The actual
prior row comes from the2024 filing; the frozen expected row is its comparative
copy in the2025 filing. Both are complete `Revenues` facts, USD597214000,
2024-01-01 through2024-03-31, with identical tag, label and description. Only
filing fiscal-year/frame metadata differ. The actual alternative was already in
the frozen materials and selected source set; the oracle enumerated alternatives
only for current-period rows. No numeric or total-versus-segment basis error was
found. The oracle, literal validators and failed result remain unchanged.
Future independent oracles must inventory permitted prior as well as current
source alternatives before execution; they must still reject different units,
durations, amounts or measurement bases.

The two unknown definitions remain unresolved. For example, gross margin using
the same quarter last year gives approximately-0.008958/neutral, while the nearest
earlier similar-duration quarter gives approximately-0.113522/negative. Generic
source-span requirements do not specify which arithmetic comparison is intended.
Changing this research definition requires an explicit policy and a new version.

The sole completed restore took1.636seconds and returned the exact saved failed
result, with0 new batches. All24 stage files stayed byte-identical:23 files in
the seal plus the seal itself. This verifies completed-file reopening, not OS
crash recovery, a Fast commit or a Slow cycle. Two independent audit harness
errors (an omitted null `start`, then dict equality on that optional instant
field) are retained; neither was a product period error.

## Why lexical selection is not the remaining fix

A separate fixed diagnostic capped query-word repetition and kept the existing
10-document selector. On the actual57-document eligible pool, latest Q1 moved
from rank46 to4; with the repaired typed reader both complete latest operands
became visible within31986characters. It also passed fixed repetition, unrelated
recency, generic required-period/source and queryless controls.

However, a frozen11-document counterexample still puts the necessary latest
source at rank11 while generic coverage reports sufficient. Independent fixed
pools additionally omit feasible older comparison, currency and conflict
witnesses. This falsifies the proposed guarantee; no ranking callback was
installed or parameters tuned to obtain a pass. The next LLM reading change is
the [explicit bounded-reading proposal](llm-signal-bounded-source-reading-proposal-20261021.md),
which remains a pending user design decision. No budget or interface change is
implemented by this diagnostic.

## Evidence and limits

- [Frozen oracle](../runs/diagnostics/current_financial_apply_20261021_v1/oracle/frozen-manifest.json),
  [source expectations](../runs/diagnostics/current_financial_apply_20261021_v1/oracle/oracle.json),
  [independent oracle review](../runs/diagnostics/current_financial_apply_20261021_v1/independent/oracle-review.json).
- [Native runner](../runs/diagnostics/current_financial_apply_20261021_v1/native/run_native.py),
  [fixed plan](../runs/diagnostics/current_financial_apply_20261021_v1/native/stage/plan.json),
  [actual result](../runs/diagnostics/current_financial_apply_20261021_v1/native/stage/result.json).
- [Independent actual audit](../runs/diagnostics/current_financial_apply_20261021_v1/independent/actual-review.json),
  [completed restore](../runs/diagnostics/current_financial_apply_20261021_v1/root/completed-restore.json),
  [restore audit](../runs/diagnostics/current_financial_apply_20261021_v1/independent/actual-restore-review.json).
- [Fixed lexical diagnosis](../runs/diagnostics/bounded_llm_source_selection_20261021_v1/driver/summary.json),
  [independent counterexamples](../runs/diagnostics/bounded_llm_source_selection_20261021_v1/independent/interface-review.json).

The private runner's11 safety controls cover irreversible execution, no model/
network/labels, actual ReviewedStore construction and immutable restore. Initial
guard, root-seal exclusion, wrapper and fixture errors are retained with their
corrected versions. These controls establish this bounded harness, not general
research recovery or new measurement capability. Product src/scripts/configs
are unchanged in this batch. Completed stages must not be reentered.

Next, retain the pending LLM-interface decision and period-definition unknowns,
and inspect the existing authorized Slow ingestion/Mining boundary. No full
successor is authorized by these partial results; overall F5/F6, feedback,
new direction/magnitude discovery/admission/reuse and engineering MVP stay open.

## Pending comparison-period decision

The [source-backed policy review](../runs/diagnostics/current_financial_apply_20261021_v1/driver/period-policy-review.json)
confirms that the old annual fixtures cannot distinguish the possible policies.
No option below is adopted, and none changes a published version or the failed
batch. Root recommends same-fiscal-window YoY gross-margin change, with revenue
acceleration measured against the immediately preceding reporting period's YoY
growth. That acceleration is more responsive to the project's3–6month question;
the alternative below measures a different, slower change. This recommendation
does not select whichever formula has sufficient GPRE data.

| Option | Gross margin | Revenue acceleration | Required evidence and limits |
| --- | --- | --- | --- |
| Adjacent-period acceleration (root recommendation) | Current margin minus same fiscal window last year | Current standalone quarter YoY growth minus immediately preceding standalone quarter YoY growth; annual growth compares adjacent fiscal years | Four matching quarter windows with proven fiscal adjacency; annual uses three annual windows. No quarter may be skipped. Cumulative YTD needs an explicit standalone basis; otherwise unavailable. |
| Same-window annual change | Same as above | Current window YoY growth minus that same window's YoY growth one fiscal year earlier | Three same-fiscal-window observations one year apart; same duration/currency/accounting basis. This is an annual change of growth, not recent-quarter acceleration. |
| Retain unknown | No new policy | No new policy | Keep both versions outside successful semantic closure and continue independent work. |

Both new-version options anchor to the newest eligible reporting window. Missing
current operands or a comparison do not authorize fallback to an older complete
pair. Preserve existing thresholds, issuer/PIT/units, evidence and failure
semantics; do not synthesize standalone quarters by subtraction, mix annual and
quarterly growth, convert currencies or overwrite old definitions. Any new
version must pass independent normal, insufficient, conflict, fiscal-calendar
and period-mismatch controls before admission. Final version numbers must be
checked for allocation when the policy is chosen.
