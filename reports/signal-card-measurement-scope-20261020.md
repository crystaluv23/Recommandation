# Exact Signal measurement scope at routing

2026-10-20. This batch addresses F4 producer disclosure, not Signal admission,
measurement behavior, score, full F4/MVP closure or new model compliance.

The completed prefix's second selector received a net-share card without its
weighted-average/comparable-period definition. Its result was unavailable, so no
wrong numeric measurement was demonstrated. Earlier exact-version/hash/catalog
checks proved identity and membership but missed the omitted measurement scope.
The actual old51 request had13cards; the independent configs-based reproduction
had11, all lacking scope. These are separate catalog inventories. The latter
reproduction and independent red tests are retained in
`runs/diagnostics/signal_card_measurement_scope_20261020_v1/`.

One Signal Library helper now supplies both `SignalCard` and actual LLM/Jev
selector cards with exact version/ref, original source types, and the complete
normalized retrieval policy. Comparison text, period/observation requirements
and source groups are copied without interpretation. No full spec, skill or
arbitrary parameters/fixtures are exposed. All existing eligible cards, routing
filters, order, PIT checks and total/LLM portfolio caps remain unchanged.

Deterministic scope separately names the actual executing callable, copies its
docstring verbatim, and discloses only configured keys explicitly declared by
that callable's `signal_parameter_names` decorator. Built-ins declare all consumed
keys, including shared thresholds, plausibility and age helpers. Defaults remain
in their documentation. Overrides use their own declaration and documentation;
unknown documentation/parameter declarations remain explicit nulls, not built-in
substitutes or evidence of missing issuer data. Returned values are independent
plain JSON, with no silent truncation or changed execution permission.

Production coordinator and worker factories create `RuntimePlanEvaluator`, which
constructs the final `SignalExecutor` map by merging defaults and supplied
overrides. Core passes that final map through an optional selector setter before
each selection. Both native selectors share the projection. A standalone selector
without injection remains unknown; old completed direct-stage freezes are not
edited or resumed under changed code.

The original v3 comparison says an implausible denominator yields unavailable,
while the actual built-in documents preserving the measured value/state with
partial coverage and confidence0.5. Both remain visible; this batch does not fix
or reinterpret that old version. A separate existing doc error for cash/current
liabilities claimed a default threshold1, although the actual shared implementation
defaults to0. Only documentation is corrected: that default and the already-supported optional
plausibility behavior for cash reserves, this ratio and drawdown. Actual behavior
is unchanged; all preexisting top-level function bodies match the prior commit
after excluding docstrings/decorators.

Validation and remaining limits:

- Existing financial/routing/Jev related tests:113 pass in5.408s.
- Independent current family:6/6 pass in0.179s, with actual core override
  injection, no-doc/undeclared unknowns, full eligible card membership, deep-copy
  isolation, exact v2/v3 scopes, weighted-average vs ending shares, and ratio0.5
  default0 versus configured threshold1.
- [Full regression](../runs/diagnostics/signal_card_measurement_scope_20261020_v1/full-tests.log):
  1868 tests in192.093s,1867 pass/1 failure from a stale description-only prompt
  assertion. Its actual routing behavior assertions passed. Only that test was
  updated to assert the new scope and issuer-data boundary; production code was
  unchanged. [Final related tests](../runs/diagnostics/signal_card_measurement_scope_20261020_v1/focused-final-tests.log):
  119/119 pass in5.493s. No second all-green full suite is claimed.
- [Lint](../runs/diagnostics/signal_card_measurement_scope_20261020_v1/lint-final.log):
  personally read fresh2026-10-19T19:36:47Z status0/PASS.
- No fresh model answers, external LLM calls, data requests, labels, scoring,
  research trajectories, Fast/Slow pointer changes or old frozen resumes occur.
- Fresh routing behavior remains pending. The smallest later exercise can reuse
  the existing bounded Signal-stage pipeline, with a real executor created and
  injected before selection; a public frozen registry variant is not an excuse
  to mislabel v2 as an ending-shares measurement. This batch builds no runner.
