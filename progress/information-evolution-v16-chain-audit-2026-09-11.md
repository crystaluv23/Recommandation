# V16 Fast/Slow execution and information-flow audit

## Actual execution

Workspace: `runs/cold_start/evolution/information-evolution-mvp-20260911-v16`.
Frozen code: `8924f2a`. Contract:
`9e89f79f8bc2bbdef1231fadce624762779bab4b95ae58da48fa0228b7131d52`.
The user authorized external execution and replenished DeepSeek balance after
V15's HTTP 402. V16 completed on 2026-09-11 local time with authoritative
`last_completed_round=1`, `last_completed_cycle=1`, and `active_cycle=null`.
It recorded 652 successful model attempts, one recoverable SSL failure and
$1.69834196 model cost. Locked Test was not accessed.

Candidate 1 completed all 24 cases, was fitness-eligible, and entered Top-K:
TP=12, FP=5, TN=5, FN=2, binary F1=0.7741935484. Candidate 2 completed 12
cases, then failed initialization in case 13 and remained diagnostic-only.
There was only one valid Plan, so cross-Plan horizontal reflection was not
exercised. This result does not establish predictive improvement over a baseline.

## Verified information handoffs

- All 36 persisted case Predictor contexts and compact post-hoc reflection
  contexts match the actual requests. Every request body's byte count and
  SHA-256 matched its persisted wire body.
- All 24 original reflections of the committed Plan survive exactly in
  `meta/round-0001.json`, alongside the Plan Critic's vertical reflection.
- Actual H1 request
  `cb4d2c2b37e1a2a5ad9a3d4c27f21befd5ec1ea152b3bc19bfbd6e75dac2a4e2`
  and its correction requests contain the exact identity-masked meta view
  (21,389 JSON characters). H1 explicitly discusses the reflection's valuation
  bridge, guidance, and existing-measurement gaps. It returned a structured
  no-testable-hypothesis conclusion, then the runtime used exploration fallback.
- The committed learning ledger contains exactly the 256 events derived from
  the valid Plan: no missing, unexpected, changed or duplicate events. Technical
  Signal failures are excluded. Candidate 2's incomplete run did not enter
  this ledger or meta history.
- The repeated point-in-time and blind-context audit covered 34 trajectories
  and 1,864 resolved document references without finding a future document,
  repeated Signal selection, or forbidden outcome/reflection field in Predictor
  input. This structural check does not prove all source parsers are complete.

## False-unavailable and recovery evidence

The earlier source-projection repair was verified live in V15, including the
completed US$2.25 billion offering in final ResearchState and Predictor citation.
In V16 candidate 2, the same financing Signal again returned a validated neutral,
partial result with exact source `sec:cik_0000895728:000110465925061164`.
Candidate 1's financing extraction instead failed citation validation. Its
Predictor view explicitly says the domain result is unknown and cannot establish
an absent condition; it was excluded from Signal learning. Availability, accepted
execution, and adoption into final research beliefs are distinct checks.

The terminal-budget repair executed successfully in three real cases. In case
13, ordinary request
`b4bc94b9c5e09a7f29342892bef670c35e5fc2d416abe927aca98262ab35c6b4`
was not transmitted. Terminal request
`cbca7511a1ef6aad8392336b4b575d9fde19ca25723a93c66d7022e9a68a35c0`
had identical research context except the mandatory-finalize runtime fields,
executed once, and produced a finalized case within 185,412 of 256,000 tokens.
Two other budget-terminal attempts also finalized. The SSL failure recovered
under the same contract, restored 14 completed cases and reused cached completed
requests before retrying the failed request.

## Slow outcome and remaining acceptance gap

No new or updated Signal reached candidate validation or promotion. Registry
version/hash remained unchanged. This is not a passed-but-not-promoted result:

- H1 produced no new testable hypothesis.
- Both E1 exploration microbatches failed citation shape validation; all eight
  cases had resolved evidence, so these failures were technical, not missing data.
- Two Update drafts were rejected during staging because `skill` was omitted,
  although the transmitted schema made it optional. A third target deferred.

Therefore pointer completion alone does not establish that this execution
successfully exercised candidate validation/promotion or a changed Registry's
visibility to a subsequent Fast run.

## Repairs after the frozen run

Specs were updated before code. The source now normalizes underscore-separated
words for temporal-intent matching, so `by prediction_time` is equivalent to prose
without changing the stored question or permitting future realized results.
Update correction and staging share the same side-effect-free candidate checks;
omitted deterministic skill means null, while LLM skill and immutable definition
constraints remain mandatory. Candidate defects are now exposed inside bounded
model correction. E1's terminal fallback independently validates each observation,
quarantines invalid ones without clipping or inventing literals, retains valid
siblings, and persists technical quarantine reasons.

Replay of the actual E1 responses preserved 19 valid observations across seven
of the eight cases that previously failed as entire batches. The real rejected
as-of guidance question now passes; a question requesting Q1 2026 actual results
still fails. The captured revenue-acceleration draft now stages in an isolated
Registry copy, but its three executable fixtures fail (two unavailable results
and one undeclared fixture source type). It was not promoted. The other draft's
incorrect target version is now reported in correction. These are local replays,
not a new external Slow cycle.

Validation: 646 full unit tests pass; repository lint and diff whitespace checks
pass. A fresh external Slow acceptance run remains necessary. Reusing committed
Fast artifacts after a completed unchanged-Registry cycle requires a top-down
spec clarification: architecture currently limits bootstrap to rejected-Fast
cold start, while the module already permits a pre-Slow committed-Fast source.
User confirmation has been requested before extending that boundary. V16's
history and frozen contract have not been rewritten.
