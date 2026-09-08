# T7 Live Execution Contract Proposal

## Current verified local state

- Code revision: `a228afc5926d13c000bcf48a7336319984690e99` before
  the preflight-interface patch in this document's checkpoint.
- New workspace: `runs/cold_start/evolution/self-evolution-t7-20260908-v1`.
- Raw Info oracle: `raw-info-8421e3b2510c4c119a14bd78a16e0823` with inventory
  hash `c230f36ceadbfcc57f3a348f59a7ec5ef474ae858c1a55e3783c6b491391e5de`.
- Stable Signal Registry: version 1, 14 Signals, hash
  `e6d9991e63d3a18783ae12900a3ed9215cb59ecf4fb6a00cfe8d3c1c4dbb25e2`.
- Approved development manifest hash:
  `13772d031162179f7468cb0e9d9aea0424f78084d18c65fe059d5b72840013e9`.
- Development splits: 8,755 Discovery cases, 16 Anchor cases, and 3,623
  Evolution Validation cases. Locked Test remains sealed and was not loaded.
- `deepseek-v4-flash` is registered and credential-ready for judge and
  evolution roles. No external request was sent during init or preflight.

Local preflight reports `ready_for_freeze=true`. This means the exact approved
development manifest is structurally valid and evaluation-feasible. It does not
authorize or imply external execution.

## Decision 1: bounded Fast/Slow pilot

Recommended pilot contract:

| Field | Proposed value | Reason |
| --- | ---: | --- |
| Judge model | `deepseek-v4-flash` | Matches the most recent real audit line and is currently credential-ready. |
| Evolution model | `deepseek-v4-flash` | Keeps the first repaired pilot comparable to the recent persisted failure evidence. |
| Fast rounds per Slow cycle | 2 | Repository's stable default; permits more than one search step. |
| Plan candidates per round | 3 | Repository's stable default; retains within-round comparison. |
| Maximum external model attempts | 250 | Bounded pilot; one tenth of the CLI default and close to recent run budgets. |
| Maximum total model cost | USD 20 | Hard cumulative ceiling, not a spending target. |
| External data acquisition | enabled | T2 requires bounded fallback when local Raw Info is contract-incomplete. |
| Data providers | `sec_edgar`, `alpha_vantage`, `massive`, `stooq` | Same explicit provider set used by the latest audited workspace. |
| Data capabilities | `company_profile`, `financial_statements`, `filings`, `filing_documents`, `news`, `transcripts`, `price_daily` | Covers current Basic Info and Signal retrieval contracts. |
| Data source types | `10-k`, `10-q`, `company_facts`, `company_news`, `earnings_call`, `earnings_transcript`, `filing`, `filing_body`, `financial_statements`, `financials`, `historical_price`, `market_data`, `news`, `price_daily`, `prices`, `sec_company_facts`, `sec_filing`, `transcript` | Avoids a wildcard authorization while preserving the audited research surface. |
| Data requests per cycle/run | 96 / 192 | Allows two cycles while bounding source acquisition independently from model calls. |
| Supervisor cycles | maximum 2 | Enough for one promotion and one subsequent Fast visibility check. |
| Consecutive no-candidate stop | 2 | Stops the pilot when two committed searches produce no candidate. |

The final freeze command must use the new post-checkpoint Git revision and will
produce a new contract hash. External execution requires a second exact command
that supplies both `--external`, `--data-external`, and that hash. Freeze alone
makes zero external calls.

## Decision 2: real-provider reliability pilot

Recommended first measurement:

- evolution-role configurations: `deepseek-v4-flash` and
  `openrouter-fusion`;
- judge-role configurations: `deepseek-v4-flash` and
  `kimi-k3-together` (OpenRouter with the fixed Together route);
- all three aliases are currently credential-ready; the run must recheck only
  boolean availability before freezing and must never persist credentials;
- 40 fresh, label-hidden requests per role/model configuration, stratified across
  ordinary, empty-result, and one-invalid-sibling inputs;
- 160 initial requests in total, at most one bounded correction per request,
  at most 320 external model attempts, and at most USD 20 total model cost;
- use frozen local role packets and tool-result fixtures; this reliability pilot
  sends no external data-provider request and exposes no web tool;
- primary rates: first-pass contract/structure acceptance and bounded-recovery
  acceptance, with exact binomial confidence intervals and raw sample counts;
- diagnostic targets: at least 95% first pass and 99% after bounded recovery;
- zero tolerance for privacy, point-in-time, evidence-lineage, frozen-cohort,
  false-promotion, or committed-pointer violations;
- maximum two looks at the same frozen pilot; failures remain in the denominator.

The 95%/99% values are proposed acceptance targets from T6, not current results.
Forty samples can expose common failure modes but cannot substantiate a 99% rate
with a tight interval; any reported conclusion must include that limitation.
The Fast/Slow pilot and reliability pilot therefore have separate USD 20
ceilings; approval of both authorizes at most USD 40 in aggregate model cost.

## Decision 3: T5 system-benefit confirmation

Recommended protocol for the first real candidate that is promoted and then
used by Fast:

| Field | Proposed value |
| --- | ---: |
| Confirmation cases | 80 cases from at least 60 issuers |
| Independent candidate-Signal fixtures | 20, including positive, negative, irrelevant, missing-data, and time-boundary cases |
| Independent repetitions | 2 |
| Maximum experiment looks | 1 before any Locked Test request |
| Primary metric | combined candidate Plan+Registry minus baseline Binary F1 |
| Minimum primary F1 gain | 0.05 |
| Minimum issuer-cluster 95% interval lower bound | 0.00 |
| Maximum coverage loss | 0.02 |
| Maximum technical failure rate | 0.05 |
| Minimum candidate measurement accuracy | 0.90 |
| Maximum cost increase | 25% |

The cohort must be drawn and reserved before the proposer, critic, Mining, or
Update sees its case contents. All four Plan/Registry arms use identical case,
source-corpus, model, output-projection, and budget identities. Missing results
produce `incomplete`; a complete run below any threshold produces `no_gain`.

These values are a reviewable proposal, not active production settings. The
repository does not encode them as defaults. Changing them after observing
outcomes requires a new protocol and cannot reuse the same confirmation cohort.
This decision approves the confirmation method and thresholds only. The exact
candidate Plan/Registry identities, frozen cohort hash, model-attempt ceiling,
and cost ceiling do not exist until a real candidate is promoted, so T5 external
execution must receive a later exact contract and authorization.

## Exact execution sequence after approval

1. Replace this document's pre-checkpoint revision with the actual checkpoint
   revision and freeze the proposed runtime contract in the initialized
   workspace.
2. Inspect `run_contract.json`, verify `locked_test_accessed=false`, and record
   its exact contract hash.
3. Run `run-cycle` or bounded `run-loop` with external model and data flags plus
   the exact acknowledgement hash.
4. Audit every persisted request/response, attempt/cost ledger, evidence span,
   case checkpoint, Registry transition, and committed pointer after each
   reached role.
5. If a candidate is promoted, run the next Fast cycle and verify its exact ref
   is selected, executed, cited, and consumed by ResearchState/Predictor.
6. Freeze and reserve the approved T5 confirmation cohort, execute all four
   arms and independent Signal fixtures, then write the immutable report.
7. Report separately: run completed, capability promoted, capability used,
   `gain_confirmed`/`no_gain`/`incomplete`, and reliability rates with counts and
   intervals. Stop at the approved cycle/look/cost limits.
