# MVP Fast/Slow Live Audit

## Scope and acceptance

The user authorized real model/data calls, prioritizing completion, general
response/error handling, and MVP scope. Acceptance requires one genuinely
committed Fast round and Slow cycle, plus inspection of actual role messages,
contexts, responses, and learning handoffs. Tests and staged cases alone do not
prove completion. A successful cycle need not manufacture a promoted Signal or
claim statistically established investment benefit.

V5 was `information-evolution-mvp-20260909-v5`, frozen
against `8ce6002` with contract
`00dd8188850abeb83db36c614c489908b81ae89e3f2661d0578f9b5737296b85`.
It uses the approved v13 development manifest, the global Raw Info oracle,
DeepSeek V4 Flash for proposer/judge, three candidates in one 24-case Fast round,
then one Slow cycle. The ceilings are 2,500 model attempts / $20 and
1,000/2,000 data requests per cycle/run. Locked Test remains outside this scope.

V5 ended at Fast/Slow 0/0 after 222 completed model attempts ($0.35506968).
Its candidates completed 4, 4, and 9 of the fixed 24 cases before their next case
failed, respectively: aggregate array capacity, evidence-array capacity, and
unrelated content drift during scoped correction. All 17 finalized trajectories
remain diagnostic-only; none entered Archive fitness or committed learning.
The context-only routing fallback did execute successfully twice in the real
run, independently of those later failures. Every persisted wire-body byte count
and hash passed inspection. This is real recovery evidence, not cycle completion.

Timing matters: at 15:45:30 China time, the reported 4/24 state was still running
and was not an error. V5's first candidate rejection was only recorded at
15:46:50, with terminal round rejection at 15:59:59. Codex account exhaustion,
assistant interruption, an incomplete live process, model output rejected by
current rules, and a confirmed implementation defect are separate categories.
Neither a zero completion pointer nor a rejected response alone proves a code
bug. The process and its terminal artifacts establish execution status.

V6 ran on `8ce6002`, contract
`b363dac567dc9da3039bb685b96e34194f8307d3e4a1e36adc4c66cd2f112adc`.
It uses the existing `gpt-4.1-openrouter` research/judge route and retains
DeepSeek for Plan proposal and Slow Mining/Update. The three-candidate, one-Fast,
one-Slow graph and validation rules are unchanged; the model ceiling is $100
with 2,500 attempts. This tests the same general boundary with another provider
instead of adding fixes for each final Flash response.

## Confirmed repairs from actual content

### Computation must precede display truncation

V3's first persisted Predictor request
`9e87cbf12dd4ff9033c822bc5f60f0f6715181abbfeba954e48f57872f407d91`
used an August price window for a September 30 prediction. The baseline helper
parsed visible Basic projections after excerpt selection and context clipping.
Thus the model and the fixed outcome label used different price origins.

| Case | Old baseline | Complete-source baseline | Correct last date |
| --- | ---: | ---: | --- |
| `cik_0000701818:20250930` | 19.996 | 23.982 | 2025-09-29 |
| `cik_0000895728:20250930` | 47.686 | 49.692 | 2025-09-29 |
| `cik_0001174922:20250731` | 91.980 | 109.614 | 2025-07-30 |

Commit `4b149db` loads the already selected complete PIT market documents through
the existing resolver, excludes rows on/after the cutoff, and computes the same
five-row mean independently of display budgets. No new acquisition or
stock-specific rule is needed. Conflicts and insufficient inputs remain rejected
or unavailable. All 624 tests passed at that checkpoint. V4's first actual
Predictor context contained 23.982 and its response correctly used approximately
47.96 as the doubling threshold. This verifies transmission, not just a helper.

### Invalid answer ownership must not destroy useful selected evidence

V4 completed five cases, then rejected case six after the routing model repeated
a partial-answer scope contradiction through both corrections. The exact last
request/response hash is
`e735f4e789af1280d87ff09d37bfc34c98e12cb1883ee043c87f4e5ac9e872d0`.
The model selected `guidance_acceleration:v1`, but both the answered rationale and
the residual claimed paying-user/revenue-impact facets. Existing quarantine
could not remove the sole selected row without turning technical failure into
an apparent no-match.

Commit `8ce6002` adds one conservative, typed recovery path. After bounded
correction, answer-ownership defects can retain that exact Signal as contextual
evidence, clear its answer scope/residual, and replace only the failed ownership
rationale with an explicit runtime explanation. All eligibility, capacity,
applicability, identity, evidence, and subsequent reflection checks still run.
The original need is preserved exactly and no new Signal or fact is invented.
Other errors retain quarantine/rejection. Events record `context_only_paths`.

Replay of the final paid V4 response now selects the same Signal and produces
`required_transition=preserve_exactly`, with three simulated attempts and no
additional real call. Tests vary diagnostic language, preserve valid siblings,
retain paid usage on a budget stop, and reject wrong typed issue/ref identities.
All 625 repository tests and lint pass at this checkpoint.

## Design and content review

| Stage | Necessary for MVP? | Content-level assessment |
| --- | --- | --- |
| Frozen inputs, attempt ledger, exact cache | Yes | Separates authorization, transmission, failed attempts, staged artifacts, and committed results. V3 exact recovery reused the first complete trajectory. A V4 sandbox-denied request remained a transport failure with no model response, not Plan fitness. |
| Shared PIT evidence preparation | Yes | Uses the same fixed cohort and checks source readiness before Plan evaluation. Readiness does not promise that the selected model projection answers every requested question. Repeating preparation on process resume is safe but adds latency. |
| Plan proposer | Yes | Actual input contains a compatible historical Plan, available source types, fixed prior, and change focus. Initial meta is empty. B and H_init change while prediction semantics remain fixed. News/filing descriptions sometimes still imply issuer ownership too broadly; preserve actual source provenance rather than expanding wording-specific guards in this MVP. |
| H_init | Yes | Turns source projections into a compact evidence state and missing-information questions. Literal numerical support and copied-claim checks caught real defects. Some compound legitimate requests were narrowed by lexical guards, such as analyst targets compared with current price; this is a quality limitation, not proof of missing data. |
| Signal routing and execution | Yes | Versioned cards restrict selection; deterministic and soft Signals remain distinct. Exact citations support soft conclusions. V4 includes both one-Signal cases and legitimate empty routing. Broad contextual choices can consume several rounds without resolving the original need; no ad hoc selection patch is added. |
| H_reflect | Yes, bounded | Carries evidence forward and keeps unanswerable needs explicit. The transition contract prevents contextual evidence from pretending to answer a need. Terminal finalization closes collection; it does not declare every question solved. |
| Blind Predictor | Yes | Actual messages mask the target and withhold outcomes; prediction is persisted before label reveal. V3 overemphasized past momentum and a one-time asset sale. V4 correctly distinguishes unlikely and insufficient-information judgments with the repaired baseline. A single prediction difference is not an improvement experiment. |
| Post-hoc, Plan critic, round meta | Yes, compact | Post-hoc receives the saved prediction plus revealed truth; it must not leak backward. Actual early reflections distinguish binary-correct insufficiency from a substantive positive thesis. Original/vertical/horizontal layers are auditable, but repeated summaries are an efficiency concern rather than a reason to add more roles. |
| Slow Mining/Update, validation, transition | Yes | Must consume committed Fast derivatives, isolate Discovery induction from effectiveness checks, and promote only validated exact candidates. Final live outcome and actual role-content review are recorded below once execution completes. |

The MVP boundary is strict on evidence, time, identity, and committed state,
but conservative about model-authored process metadata. Fix invariant violations
and exhausted-recovery dead ends; do not turn every weak explanation into a new
lexical rule. Legitimate no-match, unavailable, no-change, refinement, and failed
validation must remain separately visible.

## Final live result

V6 terminated with `round_rejected`, Fast/Slow 0/0. Candidate completion was
3, 0, and 6 cases. Two final H_init outputs contained 338/342-character beliefs;
the other failed terminal H_reflect after an all-unavailable batch. These are
actual model-output rejections, distinct from a Codex quota interruption.

The final all-unavailable batch contained only `gross_margin_change:v1`, not the
entire library. The preceding batch's `guidance_acceleration:v1` returned neutral
with partial coverage, citing Q1/Q2 management statements reaffirming production
and cost guidance. The remaining need concerned sustainable revenue beyond
one-off sales. Both selected Signals were contextual rather than direct answers;
this is a routing relevance limitation, not proof that every Signal is unusable.

MVP recovery now treats summary counts/text/bytes as compression guidance under
hard transport budgets. It retains all evidence/PIT/quantity/domain validation.
It does not truncate evidence or assert missing data means negative evidence.
A terminal all-unavailable batch returns the previous state with only finalize
changed and zero model usage. Exact paid V6 H_init outputs
`0cb4b8b72a9dc38ccaccdd46d5f71ef21a122aee290aadfcf72ea35bffddf901`
and `ba30141c9d598938b812302db6e7c01cfd3e8831e8cb738e46d5472b5edd60da`
now replay unchanged through the full remaining parser, without external calls.
A new live successor remains required; completion is not claimed.
