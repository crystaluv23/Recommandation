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


## V7 live continuation and Signal availability diagnosis

V7 is frozen at commit `6e896f6`, contract
`d3b56b5f064d3c696eea89ef4b4b058548e9c332fafaad090e819ea1bf983134`.
It retains V6 model routes, three candidates, one Fast then Slow, and the same
approved data allowlists and budget. All 625 tests and lint passed before launch.

Read-only replay of V6's Kinross `gross_margin_change:v1` produces
`execution.status=domain_unavailable` and
`Comparable SEC gross-margin periods were unavailable.` The resolution itself
succeeds, selecting the immutable financials document
`sec_edgar:cik_0000701818:financials:e6788b243ea9f3d1fd159b77`
(content hash `e6788b243ea9f3d1fd159b775d7d5a41e9b4b22ceb582aa5566012510a99c01c`).
Its namespaces are `dei` and `ifrs-full`, but `_sec_facts` parses only `us-gaap`
for raw Company Facts. It yields zero parsed facts. The source already contains
USD GrossProfit for 2023 and 2024, including filings before the prediction cutoff,
and revenue concepts `RevenueFromContractsWithCustomers` / `RevenueFromSaleOfGoods`.
This confirms an IFRS input compatibility gap (including revenue-tag mapping),
not an absent source, transport failure, or a defective gross-margin definition.
The same source can pass generic period/readiness checks before metric-specific
parsing fails; readiness is weaker than actual calculability. The running frozen
V7 implementation is unchanged while its experiment finishes.


## V7 result and generalized follow-up

V7 ended at Fast/Slow 0/0 with 4/4/0 completed cases before evidence-claim
length rejection. The earlier advisory summary change did not remove the separate
ResearchEvidenceRef 400-character cap; that was an incomplete fix. Claims now
require nonempty text without a field character ceiling. All semantic/evidence
validators still apply. New Controller outputs allow 8,000 tokens, consumed from
the frozen role limit; requests/cases/run budgets remain hard bounds. Historical
2,000-token contracts remain readable, without changing their frozen contents.

Two exact final paid responses replay unchanged through the complete current
parser: `8598257f0a49312912bd218cd0bc718ef1dd92aef4238cf9734606e8cb1c9aeb`
(claim 1,591 characters) and
`0bcf93f00686cbc7edff28f8057304bc6988152feae51a15bde9ad2bcc8b1989`
(claims 569 and 401 characters). The 658-character response
`40af8e4c3a839821e43faeb16285b1ecadce379e3098943af6240e18ad0a4a58`
still fails because current_beliefs contains a non-string item. This is a genuine
remaining output defect, not a reason to silently stringify or discard structure.

The expanded read-only audit covers 24 fixed cases and all nine deterministic
stable Signals (216 combinations), without model or data calls. The baseline,
after initial IFRS namespace/revenue mapping but before the expanded repairs,
had 47 unavailable results. It compares normal resolved documents against all
local PIT documents only as a diagnostic; broader evidence is never inserted into
formal results. Parser memoization is confined to this diagnostic process.

Confirmed input issues include missing IFRS CashAndCashEquivalents and
WeightedAverageShares aliases, CAD amounts excluded from dimensionless ratios,
and market calculations taking the final document in a tuple rather than the
complete compatible series. ONDS and DNN each already had a full selected history
(181/223 points) whose last 31 points exactly matched the selected short history,
yet momentum used only the short history. Selection is now order-independent,
latest-endpoint first and longest compatible suffix within that endpoint; conflicts
fail instead of being merged. Currency ratios match the same unit throughout;
absolute USD cash thresholds remain USD. Basic/diluted IFRS share concepts were
verified against the [ESMA taxonomy](https://www.esma.europa.eu/sites/default/files/2024-05/ESMA32-2009130576-3011_Final_Report_amending_RTS_on_ESEF_-_2024.pdf).

The audit does not equate banking net-interest revenue, an absent GrossProfit
concept, stale annual facts, or too few listing-history observations with an input
parser bug. No inferred gross profit, currency conversion, or sector-specific
revenue substitution is introduced. Full regression and repository lint pass
(631 tests); actual Fast/Slow completion still requires a new live run.


The completed 216-combination expanded replay reduced unavailable results from
47 to 28, recovering 19 combinations with no newly unavailable result. The
comparison baseline already included initial IFRS namespace/revenue support;
these 19 recoveries are additional. Four price-momentum cases recover after
correct series choice, beyond the two cases detected by the broader-document
probe (which itself still used the old order-dependent chooser). Complete results
are in [the availability audit](information-evolution-mvp-signal-availability-2026-09-09.json).
This is deterministic input recovery evidence, not Fast/Slow completion or proof
of predictive improvement.


## V8 completed cycle and MVP audit (2026-09-10)

V8 (`information-evolution-mvp-20260909-v8`, code `2526a59`, contract
`3debd4870da8b9e31ff7f0c0cf0d40f679fddbb2aaf1ccd29cb99f3cef416b83`)
committed Fast round 1 and Slow cycle 1. Both pointers are authoritative; active
cycle is null and the process exited normally. Locked Test remained sealed.
There were 471 paid-call attempts, 461 completed responses, 10 transport failures,
and $8.59047368 recorded model cost (not a measure of data-provider charges).
Every persisted wire body's byte count and SHA-256 matched its stored record.

The SSL EOF pause was retryable transport exhaustion, not a Plan defect. Resume
reused saved case checkpoints and exact request caches. A later brief user-directed
pause also recovered without losing results. Candidates 1/2/3 completed 2/24/18
cases respectively. Candidate 1 failed on non-string current_beliefs; candidate 3
failed on an invalid literal source quotation at case 19. Only complete candidate
2 entered the round checkpoint, Archive, and round meta. Its 24 finalized cases
had TP=2, FP=0, FN=12, TN=10: F1=.25, precision=1, recall=.142857.

### Content quality and historical comparison

The September 4 V112 candidate used exactly the same 24 case ids, data-manifest
hash, and realized labels/multiples. It scored F1=.636364 with TP=7, FP=1, FN=7,
TN=9. Six previous true positives became negatives, one previous false negative
became positive, and one false positive disappeared. Thus the decline is mainly
lost recall, not broad elimination of false positives. Models also changed from
DeepSeek to GPT-4.1 for research/prediction, and Plan/source packets changed; this
is not a controlled prompt-cleanup experiment and cannot establish causality.

Candidate 2 focuses Basic retrieval and research on commercialization/adoption.
Its actual negative answers often require realized customer adoption/revenue or
strong near-term confirmation, discounting clinical, strategic, expansion, and
momentum evidence. The fixed Predictor prompt explicitly permits uncertain but
source-backed opportunities and does not require a guaranteed or quantified 2x
path. The FTAI true positive itself relies largely on post-earnings momentum with
unresolved adoption evidence: a correct label does not prove strong reasoning.
The Plan reflection skill also says to use only Basic/market evidence after first
asking to reflect over the full batch; this contradictory generated instruction
is a Plan-quality concern rather than a reason to rewrite the frozen run.

The actual Plan Critic recognized lagging-indicator overweighting and missing
forward catalysts. Its first response attributed success to baseline thresholds;
the correction removed that attribution. Round meta preserved case reflections
and the candidate critique, rather than including rejected partial candidates.
Critic agreement is useful feedback, not proof that proposed causal explanations
or Signals will generalize.

### Slow result: completed control flow, unsuccessful evolution

Slow ran from 02:08:00 to 02:27:59 UTC. Registry stayed version 1 with 14 stable
Signals; there were no mined/updated/validated/promoted candidates and no candidate
effectiveness evaluations. This is NOT an MVP acceptance pass for productive
self-evolution. The detailed result is under
`experiments/cycles/cycle-0001/slow_loop_result.json` in V8.

Mining failed before an H1 model call: the outgoing identity scan matched ticker
`Z` in ordinary demographic text `Gen Z` in a representative case reflection.
Cross-case meta had also been passed to Mining without boundary anonymization.
The shared short-alias masker could additionally remove the ordinary quarter `Q2`.
This is a generic identity collision/input-boundary defect, not an issuer leak in
that particular sentence. Mining did receive the Fast reflection chain, but no
hypothesis or source comparison was produced, so downstream uptake was unproven.

Update selected customer_concentration and guidance_acceleration and made six
DeepSeek decision/correction calls. Every emitted diagnostic fact was actually a
literal substring of the supplied evidence. The hidden 240-character upper bound
misreported long, valid quotes as missing grounding; guidance's 314/267-character
quotes alone caused rejection of a legitimate `defer`. Customer diagnostics also
changed the runtime outcome relation; those semantic errors remain rejected.
The current-result evidence ids had been anonymized before document-id mapping,
producing `missing-document`, although the separate executed_evidence correctly
pointed to document-01. This contradictory packet encouraged spurious source-gap
reasoning. The Update facts/labels separation and issuer-disjoint holdout are
necessary; manually repairing a candidate or weakening its validation is not.

### Minimal generic repairs and verification

- Mask persisted meta/backlog/prior-work prose at the Mining boundary, leaving
  originals intact and preserving the outgoing guard.
- Align short ticker handling in masking and transport: one/two-character aliases
  need an explicit dollar/ticker/symbol/exchange marker. Gen Z, Q2, and AI prose
  remain intact; explicit stock identities and full company names remain guarded.
- Map document ids to opaque refs before masking result text; both evidence views
  now refer to the same source.
- Remove Update fact character ceilings; require nonempty byte-exact source text
  and retain transport budgets, source membership, schemas, and outcome relations.

634 regression tests pass. Tests cover short-alias false positives and actual
identity rejection, immutable meta masking, customer-id-bearing document references,
and long source quotes without correction. Exact paid guidance response
`7afc5ecd4c9323a95fefcf79fd7e255d20ba450b616a611febd17a2ea5fc0666`
replays unchanged as `defer`. Exact V8 meta preserves Gen Z/Q2 and passes the complete
Discovery identity guard. This is repair verification, not a new live Slow success.

### Timing and generalized handling assessment

The first Slow external call began at 02:16:31, 8m31s after Slow started. The live
process was observed at 99% CPU during local preparation. A later native sample
caught SSL reads after work advanced; it does not localize the earlier CPU hotspot.
The code scans bounded profile cohorts and builds source/identity projections;
there is insufficient evidence to blame a single function or safely skip those
boundaries. Add stage timing before targeted optimization; do not weaken Signals
or discard evidence to make this pilot faster.

The practical error policy remains: retry transport with exact cache/checkpoint
reuse; validate structure and evidence with bounded typed correction; use conservative
runtime-owned fallback only when its semantics are provable; classify data gaps
separately; retain complete sibling candidates; and record exhausted semantic
failures without turning them into knowledge. Narrative capacity belongs primarily
to transport/context budgets, not hidden field validators. Outcome associations,
source facts, and predictive quality must not be inferred from a successful exit.
A future DeepSeek run must use a new frozen contract. V8 remains immutable; its
Fast/Slow completion and audit evidence must not be replaced or relabeled.
