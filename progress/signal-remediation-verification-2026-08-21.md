# Signal Remediation Verification — 2026-08-21

## Scope

This change addresses three distinct failure layers found in the latest
evolution trajectories:

1. Raw Info requests did not reliably route to the provider adapters required
   by stable Signals.
2. Mining and Update Agents could finish without following the intended tool
   workflow or exact candidate-output contract.
3. A schema-valid Signal candidate could be promoted without proving a useful
   paired behavioral change.

The historical audit found 124 of 148 Signal calls unavailable in the latest
Plan and 827 of 1,005 unavailable across the preceding complete Slow cycle.
Those artifacts remain immutable; this verification uses isolated temporary
workspaces and does not widen an existing frozen run contract.

## Implemented boundaries

- `SignalExecutor.prepare_inputs` is the shared Registry readiness and execution
  boundary. Semantic source aliases route stable specs to SEC facts, filings,
  Alpha Vantage news/transcripts, and historical prices.
- Compatible acquisition failures are reused inside one resolver, generic SEC
  filing retrieval prefers core forms and continues past inaccessible objects,
  and Alpha Vantage transcripts are paired with earnings-history
  `reportedDate` values before becoming point-in-time Raw Info.
- A case enters Plan evaluation only when the market backbone and at least 80%
  of the frozen Registry resolve. Falling below that level pauses shared data;
  it is not counted as Plan or Signal fitness.
- Mining/Update tool cards expose exact schemas and examples. Production
  completion validators enforce the required workflow, successful candidate
  stage/test observations, bounded Raw Info views, and exact candidate refs.
  The model also receives one dynamic next required action after each turn.
- Candidate promotion now requires paired `vCurrent`/`vNext` effectiveness on
  the same stratified cases in addition to schema/capability tests. A candidate
  must change at least one result, avoid a coverage regression, and improve the
  fixed usefulness score.

## Real complete-Registry Signal apply

The final implementation was executed against the approved Discovery case
`cik_0000002488:20250530` (AMD, cutoff `2025-05-30T00:00:00+00:00`) with an
isolated data contract authorizing SEC, Massive, Stooq, and Alpha Vantage
financial, filing, news, transcript, and daily-price capabilities.

- Frozen Registry: 14 refs.
- Input preparation: 14/14 resolved.
- Effective Signal results: 13/14 (92.9%).
- Deterministic Signals: all produced evidence-backed values.
- LLM Signals: all five received complete point-in-time inputs; four produced
  evidence-backed values.
- The only unavailable result was `financing_listing_action:v1`: ten eligible
  news documents contained no financing, restructuring, redemption,
  reverse-split, or listing action. This is a semantic fail-closed result, not
  an adapter or parser failure.
- `guidance_acceleration`, `order_quality`, `commercialization_status`, and
  `customer_concentration` applied successfully to two complete historical
  transcripts. Unique case-only citation mismatches were canonicalized by
  copying the exact substring from the cited Raw Info document; ambiguous or
  fuzzy matches still fail closed.

The isolated probe contract hash was
`579ff20eebca53ff26787dea95fab23238f7b08eda95f16da32923ecc550de90`.
Its iterative verification ledger contains ten completed model attempts with
total recorded cost `0.06864088`; later replays reused exact response/data
caches. This is a one-case end-to-end smoke test, not a claim of 92.9% coverage
over the complete evaluation population.

SEC Company Facts and Massive prices succeeded. Direct SEC archive bodies
returned HTTP 403 in this environment even with a bounded user-agent; the
authorized Alpha Vantage transcript route supplied substantive LLM Signal
inputs instead of masking that provider limitation.

## Real isolated Agent conformance

Mining and Update were then invoked independently through their production
`GenericAgent` boundaries. Both completed with the exact empty
`candidate_refs` output after inspecting evidence and choosing not to fabricate
a candidate.

- Mining: seven model calls, 75,729 tokens, cost `0.02126936`; tool sequence was
  `sample_discovery_cases`, positive Raw Info search, control Raw Info search,
  `list_signal_categories`, `list_signal_cards`, and `load_signal_spec`, then
  final output.
- Update: eight model calls, 42,243 tokens, cost `0.01189020`; tool sequence was
  `list_signal_categories`, `list_signal_cards`, `load_signal_spec`,
  `query_signal_usage`, `query_signal_failure_cases`,
  `sample_discovery_cases`, and Raw Info search, then final output.
- All 15 durable attempts completed; total cost was `0.03315956`. No invalid
  tool arguments, output-schema errors, duplicate stable ids, or incomplete
  workflow finals remained.

The Agent probe contract hash was
`1fca7553282e3fc8e88e70aa95dff8419fdc08ff68fc90274daf47fca6dac8e1`.

## Remaining operational boundary

Existing v1-v5 workspaces retain their frozen data authorization and code
revision. They are audit history and are not silently widened. A fresh
workspace must explicitly authorize the required provider/capability/source
sets and configure credentials, including a compliant `SOA_SEC_USER_AGENT` for
SEC. Provider denial remains an explicit DataGap; the new readiness and fallback
logic prevents that denial from being mistaken for Signal quality.
