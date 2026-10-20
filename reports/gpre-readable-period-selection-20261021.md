# Latest financial measurement inputs: diagnosed selection gap

The completed capture source stage admits the full57-product GPRE set without
changing old records. Its two exact Registry groups each resolve17/18 inputs,
but that fraction does not prove latest-period measurement inputs were selected.
No Signal was executed in this phase.

Each group has nine financial requests. Only two select the structured Q1
document; seven omit it at the ten-document limit. Cash reserves also selects the
latest Q1 narrative filing, so these seven diagnostic flags must not be described
as seven absent latest reports or seven executed measurement failures.

The concrete cash case is independently reproducible from actual saved inputs:
[root parser probe](../runs/diagnostics/reviewed_gpre_capture_preflight_20261021_v1/independent/root-cash-readability-probe.py),
[result](../runs/diagnostics/reviewed_gpre_capture_preflight_20261021_v1/independent/root-cash-readability-result.json).
The saved `cash_reserves:v2` request asks for the latest point-in-time balance.
It selects ten of59 eligible documents, reports its generic contract satisfied,
and marks selection truncated. One selected document is the latest Q1 HTML
filing. The actual native fact parser accepts two JSON schemas and yields no
facts from that HTML. Its latest selected cash fact ends2023-12-31, in USD; the
eligible but unselected structured Q1 document provides a parseable2025-03-31
cash fact in USD. This is a demonstrated input selection/readability gap, not
an executed cash measurement or a claim about all seven outputs.

Read-only driver diagnosis reproduced all18 saved selections in each group
through filtering, deduplication, ranking and bounded selection. The seven
structured-Q1 candidates fall outside the first ten. They are PIT/type eligible;
required tags, currencies and relevant comparison periods are present. Query
ranking uses raw token occurrence counts before availability, favoring long old
annual documents. Generic source-group/period-count coverage does not ensure
the current measurement concept is readable. Cash burn and runway retain Q1
because their publication lookbacks leave only four or six candidates, all below
the limit; those controls do not establish correct ordering under truncation.

The producer is `SignalExecutor._resolve_input`; the consumer's actual financial
callable owns supported schemas, operands and latest/comparable period selection.
The producer currently passes generic source/query/coverage requirements and
omits that measurement relationship. The resolver already supports a
`select_documents` callback after PIT filtering and deduplication, and validates
its returned members and limit. A scoped repair should use this existing entry,
owned by the actual callable, preserving the ten-document ceiling and generic
fallback. It must retain needed comparative material, units, conflicts and missing
input semantics. Do not parse prose to invent a measurement contract, hardcode
Signal/company IDs, globally replace query priority, expand lookbacks or limits,
or add a permanent canonical field to conceal the mismatch.

Earlier fixture consumers had fewer candidates than the limit; source-admission
and minimum-period checks therefore passed without exercising this failure.
Actual57/59-candidate consumption exposes it. Before another model stage, verify
the original case, long old-document repetitions, applicable latest/comparable
variants, missing latest operands, incompatible units and incomplete comparison
periods through the existing selector/consumer path. F7's original0/1 and its
unverified prompt repair remain separate. No complete successor is authorized
by this diagnosis.

## Implemented repair and new bounded consumption

The actual deterministic callable now declares the same pure operand helper used
by its numeric implementation. The existing resolver callback reserves that
basis within ten documents and checks it again after selection. Exact failure
reasons, stale/latest unmatched operands, zero denominators, units and legitimate
comparison periods remain intact. Unknown callables and LLM versions retain their
original ordered selections; this is not a global recency rule.

Independent counterexamples rejected the first candidate: generic filling could
change revenue-tag dominance and abandon a feasible one-document basis, or omit
a necessary nonoperand witness. The final selector keeps a feasible minimal
basis with safe filling, or makes one bounded reverse-rank deletion pass while
preserving basis and the original retrieval contract. This is not exhaustive
subset search. [Original failures and final review](../runs/diagnostics/financial_input_selection_boundary_20261021_v1/final-review.json)
also record159 complete old/new numeric outputs or exceptions agreeing with HEAD.

The resolver now hashes complete canonical records before the callback, isolates
candidate metadata by deep copy, validates returned records and remaps IDs to the
original objects. This rejects Python-equal true/1 and1/1.0 changes and in-place
metadata mutation without poisoning the store. Legacy JSON policy is unchanged.
[Boundary evidence](../runs/diagnostics/document_selector_identity_boundary_20261021_v1/results.json)
retains the original four wrongly accepted cases; repair tests and original red
logs are preserved by the neighboring archive manifest.

The new [input-only plan](../runs/diagnostics/measurement_input_selection_20261021_v1/plan.json)
froze4265 code/source bindings after16 temporary preflight controls. Its unique
native execution completed in23.754913 seconds with exit0:
[actual result](../runs/diagnostics/measurement_input_selection_20261021_v1/result.json).
The full qualified1780-document view remains unchanged. Default v6 has six
deterministic financial requests and latest v12 has nine: all6/6 and9/9 select the
typed Q1 source. Across all nine financial-source requests, selection is8/9 and9/9;
default v6's LLM cash-ratio version still omits it. Cash's native selected latest
period is now2025-03-31 USD instead of2023-12-31. The two groups still resolve17/18,
news remains unavailable, six/seven selected sets change, all selections stay at
most ten, and every LLM/undeclared selection retains the old ID order.

[Independent terminal audit](../runs/diagnostics/measurement_input_selection_20261021_v1/independent/actual-results.json)
checks all4265 frozen bindings before/after, exact request policies and25 distinct
selected originals against the qualified view/global records. It independently
parses old/new cash periods and currency. Two auditor-only harness failures
(flat versus nested spec keys, then an overly broad path exclusion) are retained;
the product phase executed once. No duplicate prepare or Store audit was used.

This phase executes no Signal arithmetic, model, label, acquisition, append or
fullprepare, and does not reenter the completed source stage. Q1 membership does
not establish nine correct measurements or full LLM reading. The159 comparisons
are offline regression evidence, not actual bounded measurements or model behavior.

The [115-test connected check](../runs/diagnostics/measurement_input_selection_20261021_v1/root-final-focused-tests.json)
retains2 failures and12 errors, all at SEC issuer-bound fixture construction:
98 changed-path tests pass, three card tests pass, three card tests fail, and all
11 numeric-contract tests error. The39 financial/selection tests pass.
[The14 failing nodes](../runs/diagnostics/financial_input_selection_20261021_v1/issuer-fixture-diagnosis/evidence-summary.json)
are also reproduced using the exact old HEAD library blob:2 failures/12 errors.
Dependencies load from the current package first; this verifies the old issuer
and fixture entry failures, not the whole old115-test suite or later consumers.
The retained structured trace tails are original outputs, not a reconstructed
full test log. Shipped catalog capability audits consume six such unbound seed
fixtures, making this a real fixture-producer gap. Future positive fixtures need
explicit consistent synthetic issuer declarations in body and metadata; do not
guess an issuer in the auditor or rewrite published tests/spec versions. No
all-green suite or complete F5/F6/F7/MVP closure is claimed.
