# V15 terminal budget and live source-flow audit

V15 is paused at Fast/Slow 0/0 under code `1ef47d2`. It retains 23 prediction
trajectories (candidate counts 12/10/1), 435 completed model responses, one failed
HTTP 402 attempt and one interrupted attempt. Recorded model cost is $1.1029284.
The user replenished DeepSeek balance; the 402 was resolved and exact response
cache reuse plus completed-case recovery were observed before execution continued.

## Live false-unavailable repair

For `cik_0000895728:20250930`, actual request
`6215acfbf1c4fab00054dc2879228630f8407e1190cf6bfe95496ee7167db997`
now contains the previously omitted completed senior-note offering. The model
returned `financing_listing_action:v1` as neutral with partial coverage, citing
the completed US$2.25B offering, equity issuance and liquidity disclosures. The
accepted result is retained in candidate 1's complete case trajectory. The
offering claim and its source citation reach final ResearchState and Predictor.
This verifies actual execution, not merely the earlier local projection replay.

The same case's commercialization-unavailable result concerns no disclosed first
commercial delivery of a new technology; it is distinct from financing. One
guidance result in another case is explicitly `validation_failed` because a quote
touches an internal projection edge. Pure generation of learning events from the
first three actual trajectories produced 35 events from 36 results and excluded
this technical failure. No events were persisted from the incomplete round.

All 23 persisted Predictor and post-hoc contexts match actual requests, and all
request body lengths and hashes match. The 216-comparison deterministic audit was
also run on V15's frozen cohort: 28 unavailable and zero recoveries with all local
PIT documents. This does not independently establish parser completeness.

## Repeated terminal-budget gap

Candidate 1 stopped in case 12 and candidate 2 in case 10 with
`budget_exhausted`; both remained diagnostic-only with `incomplete_case_set` and
`unfinalized_case`. Neither contributed a valid Plan or meta entry. Candidate 3
was safely interrupted after its first completed case to repair the shared gap.

In candidate 1, ordinary reflection request
`8e714316fcc529b7212a724e96c59bfadcd5041d68b214911da4049443215d88`
was persisted but never transmitted. Its 33,056-byte body plus output reservation
did not fit the remaining adaptive envelope. The request still specified
`must_finalize=false`. The runtime caught the budget exception and exited, leaving
the reserved terminal budget unused. It then performed Predictor and post-hoc,
preserving diagnosis but leaving ResearchState at `continue`. The finished case
reported 167,838 tokens against a 256,000 total ceiling and 64,000 reserve.

The minimal repair catches this boundary around an already executed reflectable
batch and makes one terminal attempt using the remaining total budget. It carries
forward any paid correction usage and the identical prior state, batch and
selection intents, sets `must_finalize=true`, and uses existing full validation.
It does not increase budgets, discard cases, invent evidence or force finalize.
If the terminal reservation also fails, no second recovery is attempted; if the
result remains continue, it remains ineligible. Routing/budget exhaustion without
an executed batch retains the existing failure behavior.

Regression exercises zero-paid and paid-correction paths, terminal exhaustion and
non-finalizing output. It asserts one retry, exact state/batch identity, reserve
arithmetic, usage retention and eligibility. V16 will test the repaired boundary
in real execution with two candidates and the existing 24-case evaluation design,
then audit complete reflection persistence and actual Slow uptake. V15 is not a
completed Fast/Slow acceptance run.
