# Proof-bound market view and UTC baseline

The new five-original review materializes a separate read-only view containing
the original market record and the existing two SEC filings. Polluted news stays
excluded and transcript unknown. The old four-record review, old SEC view and
all originals are unchanged. This is a narrow source-qualification result;
independent final counterexample review has passed for this profile and its
pagination-shape boundary.

[Fresh v2 diagnostic](../runs/diagnostics/reviewed_market_snapshot_20261019_v2/result.json)
executes input freeze → production loader → reviewed worker snapshot → production
resolver factory → default Basic Info collection → the real runtime baseline
helper. Its input hash is
`0bf510e1530d7b9b6aacf015bcaae1c2ac8492ac6a70f1cc7185cbbe0b7aca5e`.
The actual baseline is 6.494 from September 23/24/25/26/29 closes, with doubling
threshold 12.988. These are saved runtime outputs from the complete qualified
source, not hand-entered stage inputs. No Predictor was called.

The independent market proof branch requires the retained old cache's exact
Massive daily endpoint and sanitized GET/adjusted/sort/limit parameters. The
original provider parser and HistoricalPriceAdapter must reproduce the entire
RawInfoDocument `to_dict()`, not only closing prices. Every bar's date, numeric
shape, source, normalization clock and metadata.prices remain bound. The HTTP
cache clock and later normalization clock are separate: all canonical bars must
share the same aware normalization instant, no earlier than the cache instant.
No arbitrary tolerance or copied replacement fields are used to force equality.

The retained historical ticker request binds issuer, symbol, date, exchange,
security type and currency. The all-type split ledger must cover cutoff UTC
date through the later old retrieval UTC date, be successful, empty and fully
unpaginated, and have been obtained no earlier than the interval it proves.
A filtered, short, premature or paginated query cannot supply that proof. This
profile does not implement post-cutoff split reconstruction. The 235 shared
unadjusted rows are optional corroboration; removing that optional proof still
admits the original 250-row record. Missing second downloads and exact cutoff-
time vendor archives are not new rejection requirements.

The first implementation had a real pagination-shape failure. Independent
review rebound origin/issuer/split proofs containing `next_url` equal to
0/false/[]/{} and all 12 variants materialized/reloaded three records. The
[old reader and executable counterexamples](../runs/diagnostics/reviewed_market_snapshot_20261019_v1/independent-review.json)
are retained beside the unmodified v1 result. A new failing regression first
reproduced the [] case. The repaired family permits pagination aliases only
when absent or explicitly null, rejecting falsey malformed values. Local checks
cover 45 malformed shapes across three aliases/three proof kinds and nine null
positives. They also retain wrong issuer/request/window/basis/numeric/time/
normalization/clock/pagination/split coverage counterexamples, and a synthetic
second-issuer/two-bar weekend/UTC-offset positive. Generic proof code contains
no company, bar count or baseline-price constants. A malformed SEC submissions
parallel array previously leaked IndexError; it now stays on the same typed
source-rejection boundary. Huge/nonfinite timestamps are also typed rejected.

Two real consumer limitations remain, explicitly separate from qualification:

- The [saved baseline timezone counterexample](../runs/diagnostics/market_baseline_timezone_boundary_20261019_v1/result.json)
  uses the same 250-row source and same instant. UTC takes September 29 and
  computes 6.494; `2025-09-29T20:00-04:00` drops it and computes 6.602. The old
  baseline uses the timestamp's local date. A saved [consumer-chain probe](../runs/diagnostics/market_baseline_timezone_boundary_20261019_v1/consumer-chain.json)
  also reproduces different acquisition windows, Basic Info observations and
  price-shape latest closes through the native parser/adapter/resolver/compute
  chain, without a live fetch. This family is not fixed here.
- Basic Info's market upstream coverage is truncated and exposes omission
  markers, while the next projection labels its one visible slice complete
  with zero omitted projections. The actual visible slice covers only part of
  the requested 45-day history. V2 saves both layers; resolved/complete does
  not prove the full interval was read. Baseline uses the full canonical source
  independently and remains correct for this actual UTC dataset input.

Independent final review replayed 27 fixed cases: all twelve old malformed
admissions now typed reject; four positives and eleven previous negatives
retain their results. Nine explicit-null positives and six alternate-pagination
alias negatives also passed independent materialize/reload checks. All 92 code,
five original and nine proof bindings and input hash match; old v1 evidence is
unchanged ([review](../runs/diagnostics/reviewed_market_snapshot_20261019_v2/independent-review.json)).

Twenty-one focused tests passed: nine market
methods plus twelve existing SEC/source boundary tests. Full offline regression:
1753 tests passed (133.765 seconds). Manual pre-push lint passed and its
2026-10-19T14:52:09Z feedback was read. They are deterministic
qualification evidence, not model behavior. No new HTTP or model call was made;
three previously retained provider GETs remain separately accounted for. Full
factory local routing, JEV/logprob mode safety, complete cohort readiness,
Predictor and the engineering MVP remain unproven. After this source checkpoint,
the daily UTC-boundary and multi-layer visibility dependencies must be resolved
before the next new model-consumption batch.
