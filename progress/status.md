# Status

Executed and audited the approved first T7 Fast/Slow pilot (2026-09-08).
`self-evolution-t7-20260908-v1` safely paused at its 250-attempt ceiling after
248 completed model responses and `$0.37523724`; authoritative pointers remain
round 0/cycle 0, Registry version 1, and Locked Test sealed. The run completed
17/24 cases for candidate 1, rejected candidate 2 on its first case, and staged
11/24 case checkpoints for candidate 3. No partial cohort received metrics or
entered Archive/learning. Exact prompt/context/response inspection found an
overlong Basic literal, two sign-inconsistent quantitative claims, one ambiguous
projection ref, high H_init/routing correction rates, and one schema-valid but
logically weak positive prediction. A generic post-correction recovery now removes
only mechanically invalid evidence rows and beliefs that lose their last identical
support, then repeats the unchanged full validation to expose layered failures;
it never rewrites raw JSON into a belief or guesses a projection. Both real final
H_init responses now replay successfully while retaining their 2 and 5 valid
sibling evidence rows. [`self-evolution-t7-live-audit-2026-09-08.md`](self-evolution-t7-live-audit-2026-09-08.md)
contains the wire-level evidence, current agent-runtime comparison, and the revised
2,500-attempt successor proposal. T7 remains open: no Fast round, Slow promotion,
next-Fast Signal use, reliability pilot, or benefit confirmation has completed.
The 2026-09-09 MVP implementation checkpoint migrates the high-frequency
ResearchState evidence failures to typed issue codes, makes deterministic
fallback independent of diagnostic wording, and reduces fixed H_init/routing
prompt bytes while preserving their contracts. Existing persistence/recovery
tests show no need for a new attempt schema. The next live workspace is prepared
for one candidate and one Fast round per Slow cycle, but freeze/execution and the
proposed 2,500-attempt/`$20` external boundary still require an exact post-commit
contract hash and approval. See
[`information-evolution-mvp-implementation-2026-09-09.md`](information-evolution-mvp-implementation-2026-09-09.md).
Fast/Slow completion, Signal promotion/use, reliability measurement, and benefit
confirmation remain open. Focused tests pass; full-suite/lint results are updated
at checkpoint completion. All 617 tests and repository lint pass.

Completed the offline portion of T6's generalized reliability matrix
(2026-09-08): [`self-evolution-reliability-matrix-2026-09-08.md`](self-evolution-reliability-matrix-2026-09-08.md)
maps format/API, evidence, recovery, persistence, generalization, injected error
distributions, and no-learning controls to deterministic acceptance tests and
the remaining live evidence. New cross-cutting tests exercise 0%, 10%,
distributed 20%, and issuer-clustered 20% technical failures without dropping
system or capability cases; valid siblings can still satisfy explicit
tolerances, while failures on supporting positive cases now reduce Binary F1.
The audit found and fixed the prior successful-row-only F1 calculation: known
positive technical failures are false negatives, and negative technical
failures stay explicit instead of becoming true negatives. Transport coverage
now includes retryable 429/5xx/timeout/URL failures, permanent HTTP errors,
refusal/no-text envelopes, unrelated provider fields, and missing usage
metadata. T1-T5 and offline T6 are complete; the real two-provider pilot,
approved statistical/reliability thresholds, and T7 live closure remain open.
All 613 tests, compileall, diff checks, and repository lint pass; no external
request was sent.

Completed T5 offline evolution-benefit confirmation tooling (2026-09-08): a
frozen, explicit protocol now compares baseline/candidate Plan and Registry in
all four combinations on the same cases, issuer groups, source corpus, model,
budget, and output projection. It records case-level predictions, failures,
coverage, usage, response identities, and executed/cited Signal refs; identical
inputs reuse one response within a replicate, while independent replicates may
not reuse an invocation. The immutable report separates contract validity,
independent Signal measurement accuracy, outcome-association diagnostics,
promotion/use lifecycle evidence, and paired system benefit. Missing system or
candidate-capability cases remain in the frozen cohort and produce
`incomplete`; a complete result below any approved threshold produces
`no_gain`. Changed Registries require an explicitly frozen independent
capability cohort and measurement thresholds. A crash-safe reservation ledger
prevents post-result cohort replacement. Existing production promotion gates
and historical Plan Archive ranking are unchanged. T1-T5 are locally complete;
T6-T7 remain open, and actual benefit is not yet established because no
confirmation protocol thresholds or external run were authorized. All 602
tests pass; no external request was sent.

Completed T2 Raw Info and Signal retrieval contracts (2026-09-08):
`RawInfoRequest` and versioned Signal retrieval policies now declare bounded
query terms plus structured required-source groups, minimum distinct periods,
period span, and observation count. The resolver selects over the complete
point-in-time eligible pool, reserves required source families and comparison
period coverage before the document limit, and continues authorized acquisition
when local evidence exists but is contract-incomplete. Coverage records expose
the exact missing requirements; unresolved partial documents and literal Basic
Info spans remain visible without being reported as answered. Signal execution
fingerprints partial inputs but gates execution until the contract is complete,
isolates that Signal from valid siblings, and maps provider, budget,
authorization, and materialization failures to technical execution statuses
instead of domain observations. The v1 seed catalog now contains explicit,
measurement-oriented queries and existing deterministic comparison/observation
requirements; no new scoring threshold was introduced. Real-shape tests cover
multi-source limiting, old comparison-period preservation, bounded acquisition
after a partial local hit, partial Basic Info visibility, Signal execution
gating, technical failure classification, round-trip compatibility, and shared
readiness. T1-T5 are complete; T6-T7 remain open. No external request was sent.

Completed T4 Slow candidate-generation hardening (2026-09-08): production H1 now
uses a versioned structured contract. The runtime owns stable proposal refs, the
fixed Discovery comparison, and evidence lookback, while the model supplies a
measurement object, canonical applicability rule, expected direction, retrieval
intent, structured falsifiers, and demand refs. Validation no longer requires
lexical overlap among model prose, query, and identifier. A non-empty capability
backlog may end in a structured `no_testable_hypothesis` result rather than a
forced candidate; its reason and H1 input fingerprint are committed and exposed
to later cycles. Signal Update now separates label-free evidence observations
from the runtime-computed outcome relation and requires each source fact to cite
a supplied document ref and literal span before association is considered.
Exploration E1 executes stable-ref microbatches; malformed batches are isolated
as technical failures, valid siblings remain, the frozen validation cohort is
unchanged, and E2 stops when either group lacks the configured grounded evidence
floor. Stable-item correction can append an explicitly missing runtime-owned
item without accepting rewrites to valid siblings. Superseded online H1 and
Update protocols and their prose-regex tests have been removed; legacy persisted
records remain readable at the compatibility boundary. An independent
fixture-driven blind set now rejects five schema-valid
Update errors (cross-case citation, fabricated literal, label-as-fact ordering,
unsupported source verdict, and missing evidence gap) while scoped correction
preserves valid sibling diagnostics. Label-revealed Mining decisions persist the
engine-derived positive/control sample basis regardless of model adapter. H3 terminal work is fingerprinted
without cycle-owned proposal ids, so exact committed refinement, rejection,
inconclusive evidence, missing evidence, and invalid-candidate work is suppressed
while changed evidence/strategy and unaffected siblings continue. Every Slow
result also stores a global search-input fingerprint, and `run-loop` stops after
three consecutive committed candidate-free cycles by default with cycle ids,
terminal categories, and changed-input diagnosis; restart checks the committed
streak before another cycle. A fresh read of V118's persisted E1 request/responses
and Slow result reproduces the original cross-domain identity rejection and the
Update claim that a positive label suggested a missing financing event, while
the new blind set targets that semantic class without rewriting history. T4's
local implementation and synthetic acceptance are complete; real closed-loop
usefulness remains a T7 question. All 589 tests and repository lint pass; no
external request was sent.

Current code organization audit (2026-09-08): the 15,507-line evolution runtime
and 12,071-line scheme engine are now stable 51-line and 17-line import facades.
Their implementation is separated into dataset, settings, transport, structured
validation, research validation, role-adapter, control, core-record, Fast Plan,
and Slow Signal modules with one-way documented dependencies; the two oversized
test modules are split by the same responsibilities. No Python file now exceeds
10,000 lines (largest production module: 6,106; largest split test: 3,330).
Canonical JSON hashing and crash-safe writes are shared by one standard-library
artifact module, and four identical backfill progress writers are one generic
implementation. The prior audit's dead-code and captured-response deletions remain
in place. Public imports, persistence schemas, external-call behavior, committed
pointer semantics, and point-in-time rules are unchanged. All 598 tests pass.

Current reliability implementation (2026-09-06): the T1 execution-isolation
foundation and the first T2 retrieval/input-representation slice from
[`self-evolution-action-plan-2026-09-06.md`](self-evolution-action-plan-2026-09-06.md)
are implemented. Runtime validation now has machine-readable issues, explicit
all/any path policy, stable item identity, and scoped projection that survives
provider list reordering while retaining valid siblings. H1 emits this contract
directly instead of granting write scope through diagnostic prose. Signal execution
now distinguishes successful/domain-unavailable observations from validation,
transport, permanent, budget, and authorization failures. Valid batch siblings
survive another row's failed correction; technical failures keep diagnostics but
are excluded from observations, learning events, and directional statistics, and
do not consume the idempotent observation key. Candidate effectiveness audits
report failures while retaining the frozen case list. Signal retrieval intent is
version-owned; the resolver ranks the complete PIT-eligible pool before limiting,
deduplicates same-source byte-identical copies, and reports query, selection, and
visible-context coverage separately. Update sees the exact evidence used by the
current Signal before supplemental windows. Aggregate Slow inputs and outputs use
one anonymity domain, and E1 refs are assigned after a cycle-bound outcome-free
ordering. Routing, Exploration E1, Signal Update, and baseline-sensitive Predictor
checks now emit the same structured issue contract; their scoped recovery preserves
valid siblings, explicitly rejects duplicate ids, and refuses to reinterpret an
all-invalid quarantined routing portfolio as domain `no_match`. The first T3
persistence slice separates immutable candidate definitions from keyed immutable
evaluations, binds promotion to one successful evaluation, deep-freezes Signal
snapshots, separates Update problem/work identity, and gives file-backed Raw Info
stores explicit snapshot/refresh plus oracle-root concurrent append semantics.
T3 promotion recovery now fails closed while a prepared transition exists and
reconciles the same batch across preparation, every stable-file class, Registry
version, output snapshot, promotion-record, and cycle-pointer fault boundaries.
T2-T5 are complete. T6-T7 remain open; no external request was sent. All 602
tests and repository lint pass.

Current V117 recovery verification (2026-09-05): inspected the real H1 request
and correction response. Validation prose incorrectly introduced `e.g` as a JSON
write path, preventing scoped correction projection. Pending recovery changes now
resolve inferred paths against the rejected object and preserve bounded Exploration
fallback after hypothesis structured-output exhaustion. All 578 tests and repository
lint pass. Exact V117 replay clears the bogus-path failure but still detects an
independent candidate-construct mismatch; it is not a successful live Mining result.
V117 used 46 model calls for $0.13163836 and committed cycle 1 with no candidates
or Registry transition. A fresh code-bound Slow run and dependent Fast verification
remain required.

Current exploration-grounding repair (2026-09-05): the post-V114 audit found
that E1's old schema forced at least one free-form observation even when a case
packet had no support, so a different model could fabricate a schema-valid
signature and let E2 discover a false pattern. E1 now accepts only either an
explicit empty observation list with a specific evidence gap or structured
observations carrying a supplied document ref and byte-exact non-trivial span.
The common local validator runs after every adapter, rejects malformed evidence,
duplicate cases, fabricated refs, and non-literal spans, and keeps the literal
authoritative over the model summary.

Exploration now reserves validation issuers first and gives each required
induction slot at most one label-hidden, same-group evidence fallback. E2 runs
only after the controller can freeze the configured grounded count in both
groups; it receives only those selected signatures, while validation cases remain
unseen. This avoids both endless deterministic retry on one empty case and
outcome-aware resampling. All 577 repository tests pass. V116 remains a zero-call
pre-change contract and must be superseded after this checkpoint; the next real
Slow run and dependent Fast verification still await explicit approval of the
named external destinations and payload classes.

Current V114 systemic Slow repair (2026-09-05): H1 produced three hypotheses and
H2 screened 32 ready profiles, but the old post-limit relevance filter erased all
36 H3 case packets before contrast. Replay against the exact Discovery and Raw Info
inputs found exact-source context for 11/12, 12/12, and 12/12 cases respectively,
but zero model-visible query matches for every hypothesis. This is a systemic
H1/data-alignment failure, not 36 independent source outages and not successful
Signal evolution. V114 remains immutable evidence: cycle pointer 1, Fast pointer 0,
Registry v1 unchanged, 48 model calls for `$0.13591368`, and 40 provider-ledger
requests including 16 acquisition reservations.

The resolver now permits a pure consumer selector over the complete eligible pool
before document truncation and reruns it after bounded acquisition; invalid selector
output fails locally, and failed-acquisition reuse binds the literal query. Mining
selects complementary bounded excerpts, keeps exact-source nonmatches as explicitly
unmatched comparator context instead of data gaps, and requires direct query-matched
packets in both fixed groups before H3 may produce any substantive decision. Thus
nonmatch can never be treated as feature absence across providers or model styles.

If H1 has no work, H3 has no usable proposal/evidence, or all H3 decisions are
inconclusive, the production adapter now invokes the existing outcome-hidden
exploration track once in the same cycle. Its candidates retain the identical
fixture, holdout, effectiveness, and promotion gates; a substantive H3 refinement
or rejection is never overridden. Update now reuses each Signal execution's exact
resolution and records all input hashes plus the bounded-excerpt limitation instead
of performing a different second retrieval. Slow output contracts remain
schema-only and Update rationale remains case-ref complete.

The next successor has 252 remaining model attempts, `$16.25695168`, and 545
provider requests. A real successor Slow run, actual prompt/context/response audit,
candidate validation/promotion, and next-Fast visibility remain required before the
MVP goal is complete. All 569 repository tests, repository lint, and whitespace
checks pass for this repair checkpoint.

Current V113 Slow audit and recovery (2026-09-04): V112's committed Fast result
was consumed through the exact committed-Fast bootstrap. V113 completed 48 model
calls for `$0.13247836` and 30 provider-ledger requests, committing cycle 1 while
keeping its Fast pointer at 0. This is not a successful Mining run: H1 used three
calls, then failed structured correction, so H2/H3 never ran; Update completed three
targets with conservative deferrals and Registry v1 remained unchanged.

Reading the actual H1 prompt/context and all three responses exposed two generic
errors: valid `positive Discovery cases` wording was rejected by an overly narrow
group-mention check, and a repaired field was discarded alongside an unrelated
rewrite. Fixed-group qualifiers now use the same grammar as the membership guard;
closed structured corrections can project only authorized model-authored paths,
restore unrelated values, and pass the complete unchanged parser. Ambiguous list
index shifts fail closed, and later corrections cannot inherit unrelated drift.
The exact V113 initial response now passes H1 in one replayed call. All 558 tests
pass. Actual H2/H3, candidate validation/promotion, and next-Fast visibility remain
unverified and required for the active MVP goal.

V111 ready state (2026-09-04): fresh contract `da7b040e...98be` is frozen
against code `fb601c7`, Python 3.12.14, and the approved development dataset.
It will run one 24-case Fast round with one candidate and then the dependent Slow
cycle, with a 64,000-token terminal reserve and V110's fully unspent ceilings of
246 model attempts, `$16.77035548`, and 618 data requests. Both freeze attempts
made zero external calls; the first failed closed until provider, capability, and
source-type wildcard allowlists were explicit. `state.json:last_completed_round=0`,
`cycle_state.json` is absent, Registry v1 is unchanged, and Locked Test has not been
accessed. Real execution remains pending explicit approval of the described external
payloads and destinations.

Current V110 semantic-consistency repair (2026-09-04): after the CLI reserve
correction, V110 froze contract `d86c1b8...55c` against code `576d02d` with one
Fast round before Slow, one candidate, a 64,000-token terminal reserve, 246 model
attempts, `$16.77035548`, and 618 data requests. Its launch was rejected before
transmission because the execution boundary requires explicit approval to send the
anonymous historical-company prompt/context to DeepSeek and bounded identifier/date
queries to the configured data providers. V110 therefore has no request, response,
attempt, or cycle artifacts; authoritative pointers remain `round=0/cycle=0` and its
full budget is unspent.

The complete V109 request/response audit found one schema-valid but semantically
contradictory Predictor result: `candidate_judgment=possible` and `magnitude=2-3x`
were accepted even though all three key reasons explicitly said the cited target was
not 2x, there was no evidence of doubling, and the divestiture was not a catalyst for
2x repricing. The Predictor prompt now requires one affirmative source-backed reason
for a positive judgment. A conservative local gate intervenes only when every reason
explicitly rejects the defined price outcome; ambiguous language, uncertainty such as
"not guaranteed", operating-metric doubling, and mixed positive/counter evidence are
left to the model. Generic alternative-path correction metadata lets any structured
role repair a sufficient subset: the Predictor may change the judgment plus dependent
magnitude or retain them and change its rationale, while unrelated fields remain
fixed and the full parser reruns. Exact V109-content regressions and both repair paths,
all 550 repository tests, and repository lint pass. Because the code changed after
V110 froze, it is immutable zero-call evidence; V111 is its fresh successor for the
explicitly approved external run.

V110 preflight correction (2026-09-04): the runtime/spec default and its unit
test required a 64,000-token terminal reserve, but the real `freeze-run` entry
still wrote the historical 36,000 value into every new contract. The CLI now
derives its frozen value from `RuntimeLimits`, and an entry-point regression plus
all 546 repository tests and repository lint pass. No V110 contract was frozen
before this correction.

Current V109 repair (2026-09-04): the first executor reached five completed Fast
cases and then stopped on a retryable TLS EOF; a mistakenly concurrent resume was
able to enter the same workspace, repeated the previously malformed initial proposer
request, received different valid content for the same `plan_r0001_c01`, and correctly
failed against the old case trajectory. Exact V109 H_init content also asked for the
issuer's adjusted close on the prediction date despite the system prompt reserving
that baseline to runtime; the missing local check accepted it and spent one useless
empty-routing call. Authoritative pointers remain `round=0/cycle=0`, Registry v1, and
V109 is immutable diagnostic evidence.

The runtime now takes a non-blocking OS lock before any cycle mutation or external
call, stages every accepted candidate Plan before its first case, and restores that
exact contract/round/slot/parent-bound Plan without another proposer call. H_init
validation now rejects scalar adjusted-close/share/stock-price lookups at the exact
prediction date or described as current/prediction-time price while preserving valid
price/volume-trend questions. Five focused regressions, both evolution modules (338
tests), all 545 repository tests, and repository lint pass. A fresh successor must be
frozen against this code revision before external execution resumes.

Current V108 repair (2026-09-04): contract `61a3324...a14a` first resumed one
retryable TLS EOF without repeating seven completed Fast cases, then made 110
completed calls plus one failed transport attempt for `$0.16910964` and five data
requests. Nine cases finalized; case ten persisted a Predictor and post-hoc result but
remained `stop_reason=budget_exhausted`, so the candidate stopped at 10/24 with
`incomplete_case_set` and `unfinalized_case`. Authoritative pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact case-ten H_reflect request had 7 prior evidence rows and explicitly capped
the result at 8, but the response appended three deterministic Signal claims and
returned 10. The correction correctly required compaction; its 24,041-byte wire body
plus 2,000-token output reservation needed 26,041 conservative units while only
16,822 remained outside the old reserve, so it was never transmitted. The old 36k
reserve also did not let a completed terminal batch spend its H_reflect portion, and a
correction preflight exception discarded already paid role usage before the Predictor.

New freezes use a 64k terminal reserve derived from the bounded terminal H_reflect
initial/correction and compact Predictor envelopes; historical 36k v7 contracts remain
readable but cannot execute across the code revision. A completed batch that reaches
the reserve receives `must_finalize=true` and may use it, while a pre-send correction
budget failure first tries the role's existing call-free fallback under the complete
unchanged parser and otherwise propagates with all paid usage. H_reflect now receives
an exact count/byte capacity map, and per-field overflow feedback states the removal
minimum without choosing evidence semantically. Focused reserve/fallback regressions,
all 541 tests, and repository lint pass. Remaining successor ceilings are 289 attempts,
`$16.83089036`, and 622 data requests.

V107 evidence (2026-09-04): contract `e7b0f90...14c7` made 61 completed calls plus
one failed TLS handshake attempt for `$0.10789268` and seven provider-ledger rows; six
case checkpoints were durable. Its same-contract retry was blocked before any request
because the bundled runtime auto-upgraded from frozen Python 3.12.13 to 3.12.14.
Exact runtime identity is a contract invariant, so V107 remains immutable evidence
rather than being modified or bypassed; V108 was frozen against the new runtime.

Current V106 repair (2026-09-04): post-`a423775` contract
`146d83f...3a8d` made 56 completed calls for `$0.07987476` and five data
requests. Five Fast cases finalized. The V105 Bumble case passed H_init after one
correction, confirming the numeric grounding repair; its routing then exhausted both
corrections on one partial guidance row. Authoritative pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact target asked for guidance about user growth, revenue, or cost savings. The
first correction correctly left only cost savings in `residual_need` and downgraded an
unrelated financing row to contextual. It retained a broad guidance selection reason;
the final correction changed that reason but again claimed cost savings, which the same
row declared unresolved. The validator was correct, but one stubborn invalid row erased
two valid contextual siblings and the whole case.

Routing correction feedback now explicitly permits whole-row contextual downgrade or
removal when an exact answered facet cannot be stated. After both corrections, a generic
call-free indexed-portfolio fallback may remove only rows named by every remaining
obligation, preserve siblings byte-for-byte/in order, and rerun the complete routing
parser. Mandatory nonempty matching and every applicability/cap validator remain
enforced. The exact V106 final response replays to the two valid contextual Signals with
an audited `selections[0]` removal; a sole mandatory invalid row still rejects. All 539
tests and repository lint pass. Successor ceilings are 141 attempts, `$17.04414696`,
and 632 data requests.

Current V105 repair (2026-09-04): post-`4b07838` contract
`541cbe5...7151` made 48 completed calls for `$0.07675780` and three data
requests. Five Fast cases finalized; case six reached H_init plus both bounded
corrections before repeating one unsupported numeric detail. Authoritative pointers
remain `round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact initial and correction requests/responses show that the model fixed every
other evidence and assertion defect, but retained `August 7, 2025` when its same-claim
literal contained only `8.7%`, Q2 2025, and 15.94%. Feedback exposed only the missing
literal `"7"`; because those characters also occur inside `8.7`, the final correction
mistook substring presence for the separately authored numeric token. Quantity feedback
now reports every missing occurrence with its field path, half-open character span,
bounded verbatim context, normalized group, and complete-token boundary rule.

ResearchState roles also have a provider-independent, no-call grounding fallback after
both corrections are exhausted. It is limited to mechanically isolated unsupported
numeric evidence/assertions. A single Basic ref may copy its existing short exact source
literal into the claim and linked assertions; otherwise invalid whole items are removed
only when evidence remains. All unlisted state is preserved and the unchanged parser and
semantic validators rerun; mixed, identity, temporal, structural, and transition errors
still fail closed. The V105 final response replays by exact-source substitution while
retaining three evidence refs. All 537 tests and repository lint pass. Successor ceilings
are 197 attempts, `$17.12402172`, and 637 data requests.

Current V104 repair (2026-09-04): post-`1081e00` contract
`2ebf1856...52f6` made 41 completed calls for `$0.06882904` and three data
requests. Six Fast cases finalized, including the case that stopped V102, before case
seven exhausted routing recovery. Authoritative pointers remain `round=0/cycle=0`,
Registry v1, and Slow unstarted.

The real target asked for fiscal-2025 guidance plus Q1 revenue and active-client
figures. The first routing response correctly removed the one-word `guidance` facet
from its partial residual, but the generic 90% token-overlap heuristic called that
residual cosmetic because the long issuer/date frame remained. It also treated shared
`figures disclosed by SFIX as of 2025-05-30` wording as an answered facet. The first
correction correctly demoted the other two inexact direct answers to contextual and
preserved the valid guidance selection; the false diagnostic then forced an impossible
second change, which the provider repeated.

High-overlap residuals are now genuine partial answers when they remove a complete
version-owned direct-answer phrase and retain none; this works for one- or multiword
measured facets without company-specific rules. Residual/reason comparison separately
excludes reporting/request scaffolding and numeric/temporal framing from substantive
topic n-grams while retaining material product/project/operating-scope checks. The
exact saved V104 first correction now replays successfully with no second call, all 533
tests and repository lint pass, and normal validation still never chooses a Signal or
writes a residual. Successor ceilings are 245 attempts, `$17.20077952`, and 640 data
requests.

Current V103 successor repair (2026-09-03): immutable contract
`4f90c4b...6e8` froze code `8388651` with 286 attempts, `$17.26960856`, and
643 data requests, but its external launch was rejected by the execution platform
because the workspace had no credits. No provider or data request was transmitted;
`state.json:last_completed_round` remains 0, no `cycle_state.json` was created, and
the contract is now superseded by the changes below.

The complete V102 request/response audit found two provider-independent defects in
otherwise accepted paths. First, fixed-semantics scanning matched `adjust` inside the
market term `adjusted close`, causing a needless post-hoc correction; action verbs now
match whole words. Second, an H_init need requested contents of a November report from
a September prediction boundary; explicit future publication dates now fail at the
exact need path while as-of questions about already disclosed future schedules remain
valid, preventing an inevitable no-result routing call.

Most importantly, the accepted KGC soft Signal cited an unrelated operations sentence
after edge correction but inherited `guidance` from the rest of its 2,000-character
projection because raw mapping widened the short quote to the whole lineage run.
Projection lineage is now clipped to the exact quote, including safe handling of
markup/entities/collapsed whitespace, and the mapped raw slice must normalize back to
that exact quote. Edge candidates must be a unique complete sentence containing the
rejected source boundary; no unrelated sentence elsewhere in an overlap is suggested.
Consequently uncited window text cannot satisfy version-owned evidence phrases or enter
H_reflect. These repairs add no normal-path LLM calls; all 532 tests pass. A fresh
post-commit contract and live Fast+Slow run are still required after credits are
available; the unchanged successor ceilings are 286 attempts, `$17.26960856`, and 643
data requests.

Current V102 repair (2026-09-03): post-`835f358` contract
`ca35d2b...e93e` made 34 completed calls for `$0.04113732` and three data
rows. Five Fast cases finalized before case six exhausted H_init's bounded recovery,
so pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact initial response used a 1,629-character market literal to support a price
range. The first correction fixed all other quantity/link defects but retained that
literal. Fresh second-correction feedback correctly required a shorter literal while
also requiring every unlisted field to remain byte-for-byte; shortening to one complete
row then necessarily invalidated the unchanged range claim and linked belief. This was
a general correction-contract dependency conflict, not a Bumble or price-range rule.
Overlong Basic-literal feedback now separates the mandatory literal path from bounded
`permitted_dependency_paths` containing only same-claim evidence claims and identical
beliefs/contradictions. Dependent paths change only when the mandatory repair would
otherwise invalidate them; all normal semantic, provenance, identity, and outcome
checks still rerun, and successful paths add no calls. Exact three-attempt recovery and
all 527 tests plus repository lint pass. Successor ceilings are 286 attempts,
`$17.26960856`, and 643
data requests.

Current V101 repair (2026-09-03): post-`10449a2` contract
`acd8908...99dc1` recorded 38 completed calls plus one failed transport attempt for
`$0.07840336` and three data rows. The generic second correction recovered two H_init
outputs and one H_reflect output that would previously have rejected the candidate;
four Fast cases finalized. Case five then stopped after both routing corrections, so
pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted.

The exact final routing context asked how operating cash flow and sale-leaseback
proceeds would fund expansion. The model correctly returned empty, but runtime treated
the three-word prefix `operating cash flow` from
`operating_cash_flow_margin` as a mandatory direct match. Both corrections therefore
invented a partial margin answer and failed scope validation. Automatic ref-derived
mandatory matching now uses only the complete normalized Signal id when it has at
least three words; it never derives sub-ngrams. Signal-owned synonyms remain explicit
version metadata, and `operating_cash_flow_margin:v1` declares only its full measured
object for direct answers. Exact V101 empty-route/full-metric regressions, all 526
tests, and lint pass. Successor ceilings are 202 attempts, `$17.31074588`, and 646
data requests.

Current V100 repair (2026-09-03): post-`e221d85` contract
`a2c3868...30ce0` made nine completed calls for `$0.01403164` and three data
rows. Plan proposal passed once; H_init, routing, and the soft Signal each passed
their correction. The first Fast case then stopped after H_reflect correction, so
pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted. The accepted
Signal evidence grounded 2025 production, cost of sales, and AISC guidance. Routing,
however, classified “latest production and cost guidance updates” as partial with a
residual that removed only `updates`; H_reflect correctly followed that persisted but
semantically cosmetic scope, and its correction restored the old need instead of the
required residual.

A partial residual that retains a version-owned direct-answer phrase while deleting
at most one content token is now cosmetic unless it is an explicit coordinated-period
split. Without a separable residual clause, correction names both scope and residual:
use full only for complete card coverage, otherwise contextualize or remove the
selection. More generally, new v7 contracts freeze two structured corrections. The
second occurs only if the primary correction remains invalid and receives the latest
output plus freshly recomputed obligations; every validator, identity/outcome
boundary, correction scope, and runtime budget remains unchanged. Historical contracts
without the limit retain one. Exact V100 scope and second-recovery tests, all 525
tests, and lint pass. Successor ceilings are 241 attempts, `$17.38914924`, and 649
data requests.

Current V99 repair (2026-09-03): post-`3230a5b` contract
`21fa5bf...ad8e7` made six completed calls for `$0.00588028` and four data
rows. Its first proposer attempt and correction were rejected before the second
proposal passed. The first Fast case then returned an empty Signal routing decision;
the exact-phrase gate forced a correction, which selected `guidance_acceleration:v1`
and failed scope validation. No case finalized, so pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted.

The actual need requested quarterly production/cost actuals compared with already
known annual guidance. The soft Signal measures fresh guidance versus prior guidance,
so the empty initial decision was correct; the bare `guidance` mandatory-route phrase
created both a needless correction and an inapplicable selection. Mandatory empty-
route phrases must now contain at least two normalized words. The seed uses explicit
update/change/revision constructions, while ordinary guidance mentions remain
available for non-mandatory model routing. For a genuinely explicit update need, the
empty correction also receives the unambiguous partial scope and literal residual
clauses discovered in V98. Exact V99 no-call replay, explicit-update correction
coverage, all 523 tests, and lint pass. Successor ceilings are 250 attempts,
`$17.40318088`, and 652 data requests.

Current V98 repair (2026-09-03): post-`f41b5cb` contract
`7cc87b1...897c` made four completed calls for `$0.00446908` and four
fetched/cache-hit data rows. The first Fast case reached H_init and routing, then its
one routing correction changed only the missing `context_tags`; no case finalized,
so pointers remain `round=0/cycle=0`, Registry v1, and Slow unstarted. The exact
target asked for production/cost guidance plus a Tasiast restart update. The selector
copied the whole target as a partial residual and claimed both facets. Correction
feedback then incorrectly derived overlap from that already-invalid residual, labeling
the answered guidance topic and possessive `s` as terms to delete.

Cosmetic residuals now use only an unambiguous, version-phrase-matched top-level
target split for reason diagnostics. The other literal clauses are exposed as bounded
`residual_facet_candidates`; ambiguous splits abstain. Possessive punctuation is not
a topic token, and exact-key shape feedback identifies missing/unexpected leaf paths
instead of the whole selection object. Runtime still neither writes the residual nor
chooses a semantic repair. Exact V98-shape replay, all 522 tests, and lint pass.
Successor ceilings are 256 attempts, `$17.40906116`, and 656 data requests.

Current V97 repair (2026-09-02): post-`df0e379` contract
`2801fb6...1679b` made 47 completed calls plus one retryable TLS failure for
`$0.06922132` and five data requests. Five Fast cases finalized before TLS resume;
resume reused their artifacts and then case six reached a mixed deterministic/soft
Signal batch before H_reflect correction failed. Pointers remain `round=0/cycle=0`,
Registry v1, and Slow unstarted. The exact need contract showed a partial guidance
answer and contextual revenue result. H_reflect adopted only revenue evidence but
applied the guidance residual. Validation correctly classified the old need as
untargeted, then contradicted itself by appending a generic remove/narrow directive;
the correction returned unchanged.

Need-transition diagnostics now attach `required_action` and the exact required need
where applicable: restore, exact partial residual, full removal, or genuine narrowing.
The aggregate instruction applies each row instead of contradicting restore actions.
No transition semantics changed. Exact V97-shape regression, all 521 tests, and lint
pass. Successor ceilings are 122 attempts, `$17.41353024`, and 660 data requests.

Current V96 repair (2026-09-02): post-`d80910b` contract
`a3ebf7d...385a1` made 57 charged calls for `$0.08348900` and five data
requests. Seven Fast cases finalized; case eight reached H_init, routing correction,
two soft Signals, and H_reflect before its sole correction failed. Pointers remain
`round=0/cycle=0`, Registry v1, and Slow unstarted. The exact Signal and reflection
requests/responses show a composite revenue claim using quantities from evidence
indices 0 and 1 while citing only index 0. The correction removed its linked belief
but retained the invalid evidence claim because Signal quantity errors, unlike Basic
quantity errors, lacked the structured literal checklist.

Basic and Signal quantity validators now emit the same missing groups, exact authored
literals, same-claim evidence paths, and linked assertions. The existing correction
contract therefore checks every retained path; runtime still neither adds a reference
nor rewrites a claim. Exact V96 feedback replay, all 520 tests, and lint pass.
Successor ceilings are 170 attempts, `$17.48275156`, and 665 data requests.

Current V95 repair (2026-09-02): post-`04dfd80` contract
`4b17497...5b646` made 39 charged calls for `$0.07100884` and three data
requests. Five of 24 Fast cases finalized before case six failed its H_init
correction, leaving authoritative pointers `round=0/cycle=0`, Registry v1, and Slow
unstarted. All 39 raw responses, every reached stage prompt/context, the six Basic
contexts, Predictor/post-hoc outcome boundary, failure artifacts, and pointers were
inspected. The proposer twice crossed H_reflect's Predictor boundary; case-one routing
claimed a period-qualified guidance facet retained by its residual; its soft-Signal
correction moved from one truncated projection edge to another; and case six changed
a rejected claim while retaining the unsupported `2025` literal.

Plan semantics are now validated at their owning `H_*` field, so operating-event
probability in H_init remains legal while H_reflect price-direction decisions receive
an exact correction scope. Reordered partial-answer overlap now recognizes two topic
terms plus a shared temporal qualifier. Signal edge feedback supplies bounded
byte-exact interior candidates without choosing evidence. Quantity correction carries
a counted per-path literal checklist, so changed surrounding prose cannot masquerade
as repair. Exact V95 replay covers all four shapes; all 520 tests and repository lint
pass. Successor ceilings are 227 attempts, `$17.56624056`, and 670 data requests.

Current V94 repair (2026-09-02): post-`e0e7215` contract
`f0d505f...0634` made three charged calls for `$0.01281336` and three data
requests. Its first Fast case stopped after H_init and its one correction, leaving
authoritative pointers `round=0/cycle=0`, active cycle 1 in `fast_loop`, Registry v1,
and Slow unstarted. The proposer and both H_init requests, full Basic projection
context, raw responses, structured correction payload, rejection artifact, and
pointers were inspected.

The first H_init response contained 32 frontier items, including five actionable
questions copied byte-for-byte into both `open_questions` and
`next_information_needs`. Its correction received eight exact eviction paths: all
five duplicate open questions plus three resolved-question bookkeeping items. Those
paths alone met both the 24-item and 6000-byte limits. However, the prompt described
the six arrays as alternative removals before the exact paths, and runtime did not
enforce ResearchState correction scope. DeepSeek consequently removed or rewrote
valid hypotheses, beliefs, evidence, and next needs while retaining four duplicate
questions; normal validation correctly rejected the result.

Exact compaction removals now override alternative arrays in provider instructions.
ResearchState correction computes a closed structural write scope only when exact
paths fill the quota and every other obligation is provably contained or satisfied by
those removals; unbounded evidence/need linkage stays open to avoid false rejection.
The actual V94 pair now replays to an explicit unrelated-drift rejection, while a
generic fixture proves one exact removal cannot authorize deleting a valid belief.
All 516 tests pass; successor ceilings are 266 attempts, `$17.63724940`, and 673 data
requests.

Current V93 repair (2026-09-01): post-`bde2375` contract
`2690f63...74727d` made seven charged calls for `$0.01263052` and four data
requests. Its first Fast case completed with one H_init, one correct empty routing,
one Predictor, and one post-hoc call and no correction; case 2 then failed one H_init
correction, leaving authoritative pointers `round=0/cycle=0`, Registry v1, and Slow
unstarted. All seven raw responses and every actual stage prompt/context were opened.
The case-1 selector saw 11 unexecuted cards but its only actionable need was analyst
targets, which none measured; no-match was logically correct. Predictor context was
anonymous and outcome-free, and the outcome appeared only in post-hoc context.

The selector's first response now included the unambiguous required-tag contract and
needed no correction. H_init also avoided cross-field question duplication. The case-2
hypothesis said the market “may be pricing in” successful execution of a 2027 opening
within the current six-month stock outlook. This already named the permitted present
expectation channel, but the local future-event guard recognized `expectation`,
`progress`, and related terms without recognizing standard `priced in`/`pricing in`
language. It therefore issued a false correction, which DeepSeek returned unchanged.
The transmission detector now recognizes the general pricing-in construction while
the direct outside-horizon causality fixture remains rejected. The same validator uses
one sentence rather than a semicolon continuation, so its one path remains one
obligation. All 515 tests and lint pass; successor ceilings are 269 attempts,
`$17.65006276`, and 676 data requests.

Current V92 repair (2026-09-01): post-`0bfac04` contract
`1b9d6b8...f84491` made 18 charged calls for `$0.02564912` and three data
requests. Its first Fast case completed all three Signal rounds, prediction, and
post-hoc reflection; the second case's H_init failed its only correction, so
authoritative pointers remain `round=0/cycle=0`, Registry remains v1, and Slow did
not start. Every persisted request prompt, complete user context, raw response,
correction payload, accepted trajectory, and failure artifact was inspected.

The actual selector system prompt contradicted itself: the literal “contain exactly”
field list omitted `context_tags`, while a later clause described up to four tags.
DeepSeek consequently omitted the field in two initial routing outputs and both paid
corrections added otherwise useful applicability classifications. `context_tags` is
now one required, possibly empty, zero-to-four-value array inside the exact field
list; runtime still never defaults or infers it, so cost reduction does not discard
Signal applicability learning.

Case 2 H_init produced three independently pathful obligations. Its correction fixed
all three quantitative beliefs and the first unsupported evidence claim but retained
the second rejected claim byte-for-byte. The validator correctly failed closed; the
prompt already contained every source projection and obligation, so neither context
loss nor a false validator caused the failure. Correction-only feedback now flattens
all obligation paths into a deduplicated `required_change_paths` list with an exact
count and final old-value comparison check. This preserves the one-correction
boundary, adds nothing to normal calls, and neither deletes nor authors evidence
locally. The first case's LLM-Signal edge-fragment correction and H_init exact-claim
correction were substantively necessary. Although the raw financing correction tried
to classify a share disposal as positive, canonical execution correctly downgraded it
to `unavailable`, and H_reflect did not adopt it.

The accepted first-case state also repeated all three actionable retrieval questions
byte-for-byte in both `open_questions` and `next_information_needs`, then transmitted
those duplicates through every reflection, Predictor, and post-hoc context. The shared
contract now assigns an exact actionable question only to the next-needs field, and
the semantic validator aggregates each new duplicate `open_questions[index]` with all
other evidence/transition errors before the one correction. It performs exact-string
comparison only, preserves committed legacy duplicates, and never infers or deletes
semantic content locally. All 514 tests and lint pass; successor ceilings are 276
attempts, `$17.66269328`, and 680 data requests.

Current V91 repair (2026-09-01): post-H1 commit contract
`4d7df7b...40223f` made six charged calls for `$0.015372` and three data requests,
then rejected its only candidate in first-case Signal routing at authoritative
pointers `round=0/cycle=0`; Registry stayed at v1 and Slow did not start. All six
actual prompts, contexts, responses, correction feedback rows, and exact cache usage
were inspected. H_init correctly removed one already answered analyst-target need and
simultaneously compacted 25 items to 24 without unrelated change.

The proposer initially returned the sole optional no-op `query: ""`; its paid
correction added a query but also rewrote all three otherwise valid H_* skills. Empty
optional query is now canonically omitted before domain construction, with the exact
raw response still cached, so no correction call or new retrieval meaning is created.
Non-string query failures carry their exact raw path, and Plan correction may change
only diagnosed B/H_* paths. The shared correction diff now descends equal-length lists
and permits list-size changes only when an element path itself is authorized, so a
named child field does not authorize rewriting or deleting its whole object.

Routing selected fresh guidance as a partial answer to a 2025/2026 guidance need and
correctly retained 2026 as residual, but the old validator treated their shared
`production cost guidance` topic as the unresolved facet. Correction was told to
delete the topic words, then still claimed both years and failed. Runtime now permits
the necessary shared topic while a mechanically visible `2025 and 2026` split makes
only the retained `2026` illegal in the answer reason. Other residual branches retain
the conservative three-term phrase/reordered-overlap gate. Correction no longer emits
a pathless clause. Exact generalized fixtures and all 513 tests pass; successor
ceilings are 294 attempts, `$17.68834240`, and 683 data requests.

Current Slow-boundary repair (2026-09-01): the latest completed bootstrap artifact,
v76b, was re-audited from its two persisted H1 requests/responses through H2, H3,
Update, validation, Registry transition, and both authoritative pointers. H1 used two
calls and `$0.00246036`; H2 was the intended deterministic canonical-applicability
stage with zero model calls. All three H1 candidates then lacked enough
hypothesis-relevant point-in-time packets in both fixed groups, so H3 durably recorded
`not_called_evidence_unavailable` and Update recorded `no_actionable_target` with
`model_called=false`. The Slow pointer advanced to one, the Fast pointer stayed zero,
and Registry v1/hash stayed unchanged through an applied empty transition.

The actual H1 content exposed cross-field construct drift: hypothesis identity and
query requested guidance or analyst revisions while `expected_positive_pattern`
could compare generic revenue growth or prior-period cost instead. H1 now derives a
normalized candidate construct from the meaningful terms shared by hypothesis id and
query, requires the expected pattern to retain at least half, and normalizes ordinary
revision word forms. A bounded correction may change only diagnosed paths and cannot
rewrite another valid hypothesis; identity-leaking outputs remain withheld and are
fully revalidated rather than echoed for byte comparison. The H1 prompt states the
same invariant to avoid preventable correction calls. All 510 tests pass. The frozen
zero-attempt v90 contract predates this runtime change and is superseded; the next
external run must use a new post-commit contract.

Current ordinary-loop repair (2026-09-01): immutable v89 contract
`e0ba705...c601aa` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 22 charged attempts, `$0.03028424`, and three
data-ledger rows. Case one completed the full Fast chain in 16 case calls; case two
failed after H_init plus correction. Locked Test remained sealed and Registry stayed
at its initial version/hash. The successor ceilings are 106 attempts, `$17.70371440`,
and 686 data requests.

All 22 actual prompts, payloads, responses, correction obligations, compact contexts,
and persisted trajectory state were inspected. Three proposer outputs contained valid
Plan objects followed by exactly one extra closing brace, creating three paid syntax
failures before the fourth call produced an accepted target-scoped Plan. Case-one
H_init was compact and material. Its first route repaired missing context tags; the
soft batch kept the valid guidance result while one financing result corrected a
cross-Signal projection citation. Four Signal rounds each contributed a new available
result or partial need transition before an explicit empty fifth route finalized.

The initial Predictor correctly returned `unlikely`: its reasons used the supplied
`23.982` mean, the `$27` target, and neutral guidance to argue against a doubling.
It described `$47.96` as the derived 2x baseline, but the validator misclassified that
threshold as the current baseline and forced correction. The correction drifted every
reason plus judgment/magnitude to `possible/2-3x`, causing the saved false positive.
Exact replay now accepts the original negative judgment. Case-two H_init then returned
25 array items against the 24 limit; correction received only a six-array choice and
returned the rejected object unchanged.

Repairs are transport/state-contract generalizations, not issuer cases. One complete
JSON object followed only by one redundant `}` is normalized with its raw hash logged;
all ambiguous suffixes still fail. Aggregate compaction now requires an exact removal
path from independently invalid items, byte-identical duplicates, then resolved
bookkeeping, without local state mutation. Predictor baseline validation recognizes
and checks `Nx/double/twice` derived arithmetic, while correction is confined to named
paths and cannot silently change judgment or unrelated evidence. Exact V89 replay,
all 508 tests, and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v86 contract
`1f8a0a1...994e4` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used five charged attempts, `$0.00936124`, and three
data-ledger rows. The first proposer response was malformed; its correction became
valid JSON but retained an H_reflect Predictor-ontology violation, so fail-closed
proposal retry produced a valid Plan. H_init and its correction then failed. Locked
Test remained sealed and the Registry stayed at its initial hash. The successor
ceilings are 167 attempts, `$17.80535132`, and 695 data requests.

All five requests/responses, including the malformed raw output, were inspected. The
accepted Plan kept every request target-issuer-scoped and separated evidence
organization from Predictor judgment. H_init received complete market/news/transcript
coverage plus six visible filing projections. The new downstream-visibility prompt
worked: its frontier retained the UBS target, production guidance, free cash flow, and
two-point market evidence. Its initial 25 items had three independently validatable
defects; correction fixed the resolved/need facet and unsupported year, but did not
remove any item for the explicit 25-to-24 aggregate obligation.

Aggregate correction feedback now adds bounded
`structurally_redundant_remove_paths` only for mechanically provable duplicates. In
the exact V86 shape, the duplicated open question / next information need yields
`open_questions[0]` as a preferred non-binding removal candidate. Runtime neither
infers research meaning nor mutates output; the normal validators rerun. Exact replay,
all 494 tests, and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v85 contract
`45b2a09...f9b22` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used seven completed model attempts, `$0.01506148`,
and four data-ledger rows. The first case completed H_init, empty routing, Predictor,
and post-hoc in four case calls; it made zero Signal executions/reflections. The
second H_init and correction then failed. Locked Test remained sealed and the Registry
stayed at its initial hash. The successor ceilings are 172 attempts, `$17.81471256`,
and 698 data requests.

All seven prompts, payloads, and responses were inspected. Case one had an explicit
SEC provider error, complete news and market context, and a single quarterly revenue /
earnings-versus-expectations need. No current Signal card directly answered that
compound need, so routing's empty selection and zero Signal calls were correct. The
Predictor received the runtime five-day mean `23.982`, returned low-confidence
`insufficient_information`, and post-hoc coherently attributed the realized non-surge
to missing fundamentals without manufacturing certainty.

H_init nevertheless retained only price evidence and omitted visible material UBS
target/Tasiast context; downstream Predictor sees this frontier, not raw Basic text.
The prompt now requires the smallest material direct expectation support or
counter-evidence when present, without enumerating every source. In case two, a Q1
year-over-year revenue/EBITDA need was falsely treated as answered by broad recent
revenue because of `company revenue`; generic company/issuer tokens are now removed
before overlap matching. Two `kind='news'` errors also split their expected-kind
clauses into pathless obligations; each diagnostic is now one exact kind-path row.
Exact V85 replay preserves the need, yields two pathful obligations, and accepts the
recorded correction. All 493 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v84 contract
`9c31bbc...fbe71` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used four completed model attempts, `$0.01383564`,
and four data-ledger rows. Proposer correction was justified: initial H_reflect said
it would finalize the four-way judgment, and correction narrowed this to evidence
collection. H_init and its correction were the other two calls; Signal routing,
execution, Predictor, post-hoc, and Slow Loop were correctly not entered. Locked Test
remained sealed and the Registry stayed at its initial hash. The successor ceilings
are 179 attempts, `$17.82977404`, and 702 data requests.

All prompts, payloads, and responses were inspected. H_init saw 14/21 company-fact
projections and 1/4 news projections with explicit budget omissions, plus complete
market and transcript rows. The same-state gate falsely treated `Kinross revenue` as
a resolved topic between a historical-revenue question and a gold-price sensitivity
question. Its conservative two-word fallback now removes possessive remnants and
abstains when both phrases begin with the same title-cased entity token; semantic
lowercase topics such as construction progress remain eligible.

Although V83 had structured missing quantity groups, V84 showed that normalized
`4239700000` was not an actionable spelling for `$4,239,700,000`; correction copied
the rejected claims unchanged. Missing-quantity obligations now also carry the exact
numeric substrings found in each claim and instruct a grammatical single-observation
narrowing when one comparison endpoint is removed. Exact V84 replay removes the false
topic obligation, maps all normalized groups to authored literals, rejects the
recorded response, and accepts four source-supported claims with matching beliefs.
All 491 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v83 contract
`e0014d5...7beff` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used four completed/charged attempts, `$0.00985460`,
and four data-ledger rows. The first proposer output had one extra closing brace; its
raw response and usage were durably preserved and the sole correction produced a
valid Plan. H_init and its correction were the other two calls; Signal routing,
execution, Predictor, post-hoc, and Slow Loop were correctly not entered. Locked Test
remained sealed and the Registry stayed at its initial hash. The successor ceilings
are 183 attempts, `$17.84360968`, and 706 data requests.

All four requests and three persisted model responses, including the malformed raw
proposer output, were inspected. H_init saw complete 4/4 market and 5/5 news coverage,
an explicitly unavailable 10-K request, and 13/18 earnings-call projections with five
budget omissions. Its initial state was compact, but the local same-state check
mistook the shared period `Q2 2025` for a topic and falsely said a gold-price question
was answered by a production-cost question. Pure temporal phrases no longer establish
resolved/need equivalence.

The same market claim containing an unsupported computed `25.7%` appeared on two
evidence refs. Old feedback named only the first, then exact-copy diagnostics offered
the still-invalid second ref as a valid candidate. Missing-quantity obligations now
carry every same-claim evidence path and normalized missing group, require one
identical retained repair, and exclude every named evidence index from copy candidates.
Exact V83 replay removes the false period obligation, names both market refs, excludes
their claim from candidates, rejects the recorded response, and accepts a complete
model-authored repair. All 490 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v82 contract
`897e949...14d74` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used three completed model attempts, `$0.00532476`,
and three data-ledger rows. The candidate Plan, H_init, and its one correction were
the only calls; Signal routing, execution, Predictor, post-hoc, and Slow Loop were
correctly not entered. Locked Test remained sealed and the Registry stayed at its
initial hash. The successor ceilings are 187 attempts, `$17.85346428`, and 710 data
requests.

All three real V82 prompts, payloads, and responses were inspected. The accepted Plan
had three target-company-scoped requests; H_init saw complete request coverage of
4/4 disclosures, 5/5 news projections, and 3/3 market projections. It returned a
compact state. Initial correction feedback correctly named one invalid multi-row
market claim and two quantitative beliefs without byte-exact evidence claims. The
correction fixed the claim and Asante belief but changed the valid evidence wording
`Kinross's` to `Kinross Gold's`, leaving one exact-link failure. This was model
noncompliance rather than a hidden validator or contradictory prompt.

Grouped quantitative assertion obligations now add at most three path-specific exact
claim candidates, ranked only from evidence rows with no independently reported
defect. The role may copy one, remove the assertion, or repair a different evidence
claim and copy its final value; runtime still makes no semantic replacement. Exact
V82 replay ranks the correct final-price claim first for the failed belief and accepts
a one-field byte-exact repair. All 488 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v81 contract
`713719f...10d46` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used three completed model attempts, `$0.00965076`,
and three data-ledger rows. The candidate Plan, H_init, and its one correction were
the only calls; Signal routing, execution, Predictor, post-hoc, and Slow Loop were
correctly not entered. Locked Test remained sealed and the Registry stayed at its
initial hash. The successor ceilings are 190 attempts, `$17.85878904`, and 713 data
requests.

All three real V81 requests/responses and all visible Basic projections were
inspected. Request-fair context live-covered every resolved request: company news
5/5, market 4/4, the nominal competitor request 3/3, and earnings calls 12/19 with
seven explicit budget omissions. The competitor request itself was unsound: Basic
Info always resolves under the target `company_id`, so its general cross-issuer
description/query merely returned more target-company news. Automatic Plan
validation now rejects such fields before case data or H_init calls; competitive
requests must explicitly use the target issuer's own disclosures or company-scoped
news.

H_init returned 32 items, asked for the runtime-owned baseline date/price, attached
two non-literal temporal/quantity claims, and authored eight quantitative beliefs
that did not copy their evidence claims. Its correction fixed most citations but
removed only four items and retained the baseline question. Raw validation now names
that exact question path, groups all quantitative assertion paths into one checklist,
and makes combination overflow computationally explicit with current total, maximum
total, and minimum removals; removing a belief/evidence pair counts as two. Exact V81
replay yields `32 / 24 / 8`, rejects the recorded 28-item correction, and accepts a
24-item repair. All 487 tests and repository lint pass.

Current ordinary-loop repair (2026-08-31): immutable v80 contract
`6e9b69f...8d284` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used three completed model attempts, `$0.00525840`,
and three data-ledger rows. The candidate Plan, H_init, and its one correction were
the only calls; Signal routing, execution, Predictor, post-hoc, and Slow Loop were
correctly not entered. Locked Test remained sealed and the Registry stayed at its
initial hash. The successor ceilings are 193 attempts, `$17.86843980`, and 716 data
requests.

The new projection coverage fields live-verified correctly: both Plan requests were
source-resolved and `projection_status=complete` with 5/5 visible projections. H_init
returned a compact 23-item state. Its actual citation defects were limited to one
claim adding a date found only in metadata and the linked belief not copying that
claim. The correction removed the date and returned four valid literal refs.

Rejection instead came from the new same-state stale-need check tokenizing every
`Kinross Gold's ...` question as the shared phrase `kinross gold s` and falsely
marking four unrelated needs as resolved by the stock-performance question. The
model reasonably preserved them. Topic matching now removes possessive remnants and
current/recent/latest boilerplate, prefers an ordered three-word topic, and allows a
two-word fallback only when it is not title-cased as an issuer name in both strings.
The exact V80 initial/correction replay now yields only the two real quantitative
obligations and accepts the recorded correction without another call. All 485 tests
and lint pass.

Current ordinary-loop repair (2026-08-31): immutable v79 contract
`e208df2...d8f8` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used eight completed model attempts, `$0.01779036`,
and three data-ledger rows. KGC completed and persisted Predictor plus post-hoc
output; Wynn failed after its H_init correction reduced a 33-item ResearchState by
only two items. Locked Test remained sealed and the Registry stayed at its initial
hash. The successor ceilings are 196 attempts, `$17.87369820`, and 719 data requests.

All eight real V79 requests/responses were inspected. The KGC H_init correction fixed
its quantitative belief but retained a request for the latest analyst target/rating
even though the same visible news projection said UBS raised the target from `$20` to
`$27` and reiterated Buy. Routing correctly returned empty and spent no Signal calls,
but the already-answered need then survived into Predictor, which otherwise used the
new runtime baseline `23.982` correctly. H_init raw prevalidation now aggregates a
high-confidence visible-answer signature and same-state resolved/need contradiction
with citation and compaction errors before the only correction; it reports one exact
need path and bounded source excerpt, abstains on partial matches, and never rewrites
the need locally.

The real Wynn error said only `combined count=33 > 24`; it did not say that at least
nine items must be removed or which arrays were alternatives, so correction returned
31. Combination obligations now carry `minimum_removed_items` and
`must_reduce_any_of_paths`, while per-field overflow remains field-addressed. Exact
Wynn replay gives the nine-item minimum plus the duplicated construction-progress
need path in one correction and accepts a 15-item model-authored repair.

The actual Basic Info input exposed a second control-plane ambiguity: earlier news,
market, and transcript requests consumed the sequential 48k/32k budgets, leaving the
resolved financial request with zero visible projections and no omission marker.
Both durable span and model projection allocation now retain one highest-ranked item
per resolved request before filling remaining capacity, without increasing either
ceiling or clipping a span. Each model request explicitly separates source `status`
from `projection_status` and visible/omitted counts, which also survive in the
Predictor source index. Exact KGC/Wynn replay, all 484 repository tests, and lint pass.

Current ordinary-loop repair (2026-08-31): immutable v78 contract
`8d55189...504c4` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 12 completed model attempts, `$0.01447992`, and
three data-ledger rows. The first KGC case finalized and persisted Predictor plus
post-hoc output; Wynn then failed after its empty routing correction. Locked Test
remained sealed and the Registry stayed at its initial hash. The successor ceilings
are 204 attempts, `$17.89148856`, and 722 data requests.

Every real V78 request/response was inspected. Empty routing feedback named neither
the matching Signal's target need nor an output path, so correction copied an unrelated
need and omitted tags; feedback now identifies top-level `selections`, ref, target
index, and phrase. KGC routing also claimed Tasiast restart coverage in
`selection_reason` while retaining the same facet in `residual_need`; partial reasons
may no longer repeat a distinctive residual phrase. Its soft-Signal correction was
not sent because a 55,761 exact reservation exceeded the 54,735 remaining case
budget. The correction had duplicated both rejected rows and incorrectly required one
quote even for current/prior comparisons. It now omits durable failed output, permits
the smallest skill-required quote set, and the exact V78 repair reservation is 53,478.

The completed KGC Predictor received no runtime five-day mean and mislabeled the old
`$19.38` observation as current, then post-hoc repeated the resulting wrong target
upside as a decision driver. The bounded Predictor packet now carries a point-in-time
five-day baseline derived from visible Basic market rows (`23.982` in the exact V78
replay); local correction rejects another dated observation labeled current/baseline,
and post-hoc retains the same baseline. H_init now distinguishes expectation repricing
inside six months from operating events occurring later, and numeric correction
advice no longer creates pathless semicolon obligations. Exact V78 routing/Predictor
replay, all 480 repository tests, and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v77 contract
`449e5fe...b9aca` rejected its only candidate during the first case at authoritative
pointers `round=0/cycle=0`. It used four completed model attempts, `$0.00602560`, and
three sandbox-denied staging data rows. Plan proposal and bounded H_init passed in one
call each; routing failed after its one correction. Locked Test remained sealed and
the Registry stayed at its initial hash. The successor ceilings are 216 attempts,
`$17.90596848`, and 725 data requests.

The exact initial routing output omitted `context_tags` on two rows. The parser treated
that routing-only shape defect as terminal for each row and hid already decidable
semantic errors until after correction: guidance pointed its residual at a different
analyst-estimate need, while customer concentration retained the complete generic-risk
target and lacked both required customer context and a direct-answer phrase. Current
routing continues semantic diagnosis when only tags are missing/invalid, without
inserting a tag into accepted output. A partial residual must now retain at least half
of its own non-generic topic terms from the one selected target and remove at least ten
percent of the target's topic terms. Internal routing diagnostics no longer create
pathless semicolon fragments. Exact V77 replay yields six path-bearing obligations and
accepts one minimal guidance-only correction; all 476 tests and lint pass.

Current Slow-bootstrap verification (2026-08-30): immutable v76b contract
`e0b0b6c...3462` committed authoritative `cycle=1` with zero Fast rounds, two
completed H1 calls, `$0.00246036`, and 13 data-ledger rows (one local sandbox error,
seven fetched, five quota-deferred). It used current runtime code with the compatible
v31-v33 frozen no-signal backlog and its Registry hash; the current ordinary Registry
had no eligible no-signal bootstrap source. Locked Test stayed sealed. H1 proposed
three grounded hypotheses, its correction removed fixed-group redefinitions and one
alternate horizon, deterministic H2 built 32 anonymous ready profiles with zero model
calls, and H3 was correctly not called because only one of 36 bounded evidence packets
was usable. With no candidate, Update made zero calls and the Registry transition was
an applied no-op. The remaining cumulative ceilings are 14 attempts,
`$17.91199408`, and 728 data requests.

Exact v76b correction artifacts exposed that semicolons inside four H1 diagnostics
had been split into eight obligations and every `must_change_paths` array was empty.
H1 validation now names exact hypothesis fields and keeps matched text within the same
obligation; replay of the real initial/corrected responses produces four obligations
with four exact paths. ResearchState-only quantity/claim repair prose is no longer
sent to unrelated roles, reducing this H1 system prompt from 5,792 to 5,176 characters
while preserving a byte-identical initial/correction prefix and all validators. The
real V76 response replay, all 475 repository tests, and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v75 contract
`7de3a6f...f019` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 11 completed model attempts, `$0.01025724`, and
four data-ledger rows. The first Fast case finalized and persisted Predictor plus
post-hoc output. Locked Test remained sealed, the Registry stayed at its initial hash,
and Slow Loop did not start. The successor ceilings are 16 attempts,
`$17.91445444`, and 741 data requests.

V75 live-validated the new routing schema. The first current selector response used
`answer_scope=partial` for the revenue-growth facet, persisted the exact residual
product-adoption need, and kept a second growth Signal contextual on the same target.
Its only defect was two missing `context_tags` fields; correction added only those
fields and preserved the scope/residual byte-for-byte. Both deterministic results were
unavailable because the Plan's 10-Q request resolved to provider-no-data, so runtime
correctly performed no H_reflect and a later empty routing decision finalized the case.
Post-hoc correction replaced prohibited probability language with confidence language.

The second H_init response had two independently reported defects: a missing evidence
`kind`, and unsupported `2025` in both the evidence claim and linked belief. Correction
fixed only the first and repeated the second. Aggregating several requirements into a
semicolon-delimited string is therefore not enough to make one correction executable.
Every role correction now receives the unchanged complete error string plus a numbered
`obligations` array, `obligation_count`, and extracted `must_change_paths`; the system
requires every row to be satisfied. This projection adds no semantic inference or
local repair, and the exact same parser/validators still run after the one correction.
The V75-shaped regression remains covered and all 475 tests plus lint pass.

Current ordinary-loop repair (2026-08-30): immutable v74 contract
`053795a...3fe2` rejected its only candidate during the seventh case at authoritative
pointers `round=0/cycle=0`. It used 50 completed model attempts, `$0.05659276`, and
three sandbox-denied data-ledger rows. The first six Fast cases finalized and
persisted Predictor plus post-hoc output. Locked Test remained sealed, the Registry
stayed at its initial hash, and Slow Loop did not start. The successor ceilings are
27 attempts, `$17.92471168`, and 745 data requests.

Three actual H_reflect requests live-verified the V73 result-aware interface. Enbridge
adopted no context-only evidence and preserved its state; Life Time adopted exact
cash/margin/growth claims while preserving every context-only need; Bumble adopted
two direct-answer claims and changed only their targeted needs. Deterministic claims
occurred once per result, unavailable evidence indices were hidden, routing-only
fields were absent, and each call passed in one attempt. One optional soft correction
was refused before transmission when it exceeded the adaptive reservation; its valid
sibling survived and the case still finalized, so no extra call was spent.

The exact Bumble output also showed that target identity alone cannot police compound
needs: selection reasons said that revenue growth and cash position answered only one
facet, but reflection deleted the remaining user-metrics and buyback/strategic-plan
facets. Current routing therefore persists `answer_scope=full|partial`; partial answers
must provide an exact residual need, and one routing round permits only one direct
answer per target. H_reflect receives that action and local validation requires removal
for full scope or exact residual replacement for partial scope. Non-answer and
unavailable actions still require preservation; old selections without scope remain
readable through the generic legacy path.

V74's terminal H_init failure was a separate correction-usability defect. The source
said `Stitch Fix, Inc. (SFIX) reported...`; initial and correction both returned the
absent paraphrase `SFIX reported...`. Strict rejection was correct, but feedback only
reported zero matches. Substantially overlapping absent Basic literals now receive
one at-most-800-character exact window from the named visible projection, together
with the rejected value and occurrence count. This is diagnostic only: the model must
still author a new ref and full byte-for-byte validation is unchanged. The two exact
V74 regressions plus all 475 repository tests and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v73 contract
`7454f12...84f` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. It used 13 completed model attempts, `$0.02261952`, and
four data-ledger entries (three sandbox-denied preflight rows plus one external SEC
fetch). The first Fast case finalized and persisted Predictor plus post-hoc output;
the second reached bounded H_init, corrected routing, corrected soft-Signal execution,
and both H_reflect attempts. Locked Test remained sealed, the Registry stayed at its
initial hash, and Slow Loop did not start. The successor ceilings are 77 attempts,
`$17.98130444`, and 748 data requests.

Exact V73 inspection verified the V72 state-frontier repair live: H_init used 866 and
868 output tokens, returned bounded arrays, and its one correction changed only two
numeric beliefs whose strings did not match their cited claims. Routing correctly
reclassified a contextual revenue result from `answer_need` to `combine_evidence`,
and the soft-Signal correction correctly made guidance unavailable because the visible
source had no management guidance, outlook, or forecast. No extra H_reflect was used
on the first naturally completed case.

The second-case H_reflect adopted canonical `cash_reserves=2.07009e+09`, but rewrote
it as an unsupported `$2.07 billion`, removed the context-only revenue need, and kept
the directly targeted liquidity need. Its correction received the complete batch and
prose selection intents but repeated the same invalid state byte-for-byte. The model
view now exposes a deterministic exact claim once at result level, omits its repeated
evidence/interpretation copies, strips routing-only fields from executed intents, and
supplies one deterministic result-aware rule per prior need. Only adopted evidence
from an available direct-answer ref authorizes narrowing its named need; contextual
and unavailable refs require exact preservation. Local validation uses the same
availability boundary and hides unavailable evidence indices. The V73-shaped
regression plus all 472 repository tests and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v72 contract
`e771419...8aab` rejected its only candidate during the third case at authoritative
pointers `round=0/cycle=0`. It used 23 paid model attempts—22 completed plus one
malformed response—`$0.03103324`, and four fetched/cache-hit SEC request-ledger
entries. The first two Fast cases finalized and persisted Predictor plus post-hoc
output. Locked Test remained sealed, the Registry stayed at its initial hash, and
Slow Loop did not start. The successor ceilings are 90 attempts, `$18.00392396`, and
752 data requests.

Exact third-case H_init inspection found a 44,946-byte request containing the bounded
38,855-character Basic projection. The response used exactly all 2,000 output tokens
and ended inside `supporting_evidence[0]`: before truncation it had enumerated 52
`current_beliefs`, ten open questions, ten next needs, and five resolved questions.
Its correction retained the same full Basic context and correctly became compact, but
paraphrased the first source literal (`Enbridge is considering...`) instead of copying
the visible contiguous text (`Canadian pipeline operator Enbridge Inc. is
considering...`). Strict literal rejection was correct; the design defect was that
the initial ResearchState contract had no compactness bounds, so its sole correction
was consumed by preventable transport truncation before semantic citation repair.

Provider-authored ResearchState is now a bounded decision frontier rather than a
second source summary: default field caps are 3/8/8/4/6/6/6, all arrays total at most
24 items, non-evidence text is at most 300 characters, initialize Basic literals at
most 800 characters, and canonical JSON at most 6,000 UTF-8 bytes. Raw prevalidation
aggregates every count/item/literal/byte violation without dropping content. A
full-token incomplete JSON response receives explicit truncation feedback. H_reflect
uses the larger of defaults and prior observed counts/bytes, so an old over-limit
checkpoint can be preserved but cannot grow; unchanged legacy long text remains
readable. Complete Basic/Raw Info/Signal/trajectory artifacts remain local. Three V72
regressions plus all 471 repository tests and lint pass.

Current ordinary-loop repair (2026-08-30): immutable v71 contract
`b4bd1e1...34a68` rejected its only candidate during the fifth case at authoritative
pointers `round=0/cycle=0`. Its preflight plus run used 30 completed model attempts,
`$0.03733464`, and five fetched/cache-hit SEC request-ledger entries. The first four
Fast cases finalized and persisted Predictor plus post-hoc output; case five reached
H_init, three routing rounds, one soft-Signal call, and two H_reflect calls before the
last routing correction failed. Locked Test remained sealed and the Registry stayed
at its initial version/hash, so Slow Loop did not start.

Exact case-five inspection covered all ten persisted requests and responses. H_init's
36,810-byte body used a bounded 31,015-character Basic projection and cited one literal
membership-revenue clause. The 43,144-byte guidance request returned canonical
`unavailable` because its visible projection contained no management guidance.
H_reflect then adopted only available revenue, cash, and operating-cash-flow results;
it correctly retained membership-count, future-projection, and capex/funding needs
that those contextual results did not answer. Its 9.1-9.5k-byte compact requests did
not repeat Raw Info. These state transitions match the design.

The failure was routing correction layering plus an over-strict new schema rule. In
three consecutive routing rounds, the model attached a need index to
`combine_evidence` to record which need the context supported. Runtime treated this
reasonable association as invalid and spent corrections clearing it. In the last
round, the initial output also selected `customer_concentration:v1` by analogy from
generic revenue-shortfall risk even though no current need/state named a customer,
client, order, or backlog. Validation reported only the non-answer targets; correction
cleared them, then the already-visible customer applicability error exhausted the sole
repair and discarded a separately plausible financing selection.

Current selection semantics allow any reason to retain zero or one valid association
index, while `answer_need` alone requires a target and alone authorizes H_reflect to
remove or narrow it. This preserves attribution without creating false resolution or
unnecessary calls. Routing now aggregates every structurally usable item's index
shape/bounds, reason/role, version-owned exclusion, required-context, and direct-answer
failure in the first feedback, naming selection paths/refs; malformed items remain
fail-closed and no error is repaired locally. The V71-shaped regression preserves the
financing association, reports customer applicability together with an independent
invalid index, and passes after one minimal correction. All 468 repository tests pass.
The successor contract must freeze 113 attempts, `$18.03495720`, and 756 data requests;
v71 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v70 contract
`406f5f1...b71e2` rejected its only candidate during the fourth case at authoritative
pointers `round=0/cycle=0`. Its preflight plus run used 32 completed model attempts,
`$0.04067616`, and three successful/cache-hit SEC request-ledger entries. The first
three Fast cases completed H_init, all reached an evidence-exhaustion finalization,
and persisted Predictor plus post-hoc output. The fourth case reached H_init, routing,
soft-Signal execution, and both H_reflect attempts before rejection. Locked Test
remained sealed and Slow Loop did not start.

Exact Wynn artifacts exposed a cross-role attribution defect. The router called
`customer_concentration:v1` a direct answer to a request for specific recent customer
contracts, while its available result cited only strength across three sales channels.
H_reflect correctly kept the still-unanswered contracts need and therefore could not
satisfy the old coarse “remove any need” correction. An earlier completed Wynn
trajectory showed the more dangerous inverse: after adopting cash reserves and Q1
YoY revenue growth, correction deleted the unrelated Q2 revenue/EPS-versus-expectations
need, retained the compound debt/liquidity need unchanged, and passed. A routine Q2
earnings-release date was also accepted as neutral financing evidence.

Current selection output therefore binds every `reason_code=answer_need` to one
pre-execution `target_need_indices` entry; all other reasons carry an empty array.
Optional version-owned `routing_answer_need_phrases` separate direct need coverage
from contextual applicability. H_reflect receives the persisted target and, in both
continuing and terminal reflection, must remove or genuinely narrow only that target
while preserving every untargeted prior need byte-for-byte. Legacy committed
selections without the field remain readable. `customer_concentration:v1` now
requires customer/order objects in available evidence and directly answers only
concentration/dependence/diversification needs. `financing_listing_action:v1` rejects
routine-event evidence, while revenue-growth, cash, guidance, customer, and financing
versions expose bounded direct-answer objects. Exact v70 artifact replay changes the
customer selection to contextual and rejects the channel and routine-event evidence.
All 467 repository tests pass. The successor contract must freeze 143 attempts,
`$18.07229184`, and 761 data requests; v70 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v69 contract
`4333c20...aab2e` rejected its only candidate during the second case at authoritative
pointers `round=0/cycle=0`. Its preflight plus run used 12 completed model attempts,
`$0.01503012`, and three successful/cache-hit SEC request-ledger entries. The first
KGC case completed H_init, natural empty routing finalization, Predictor, and post-hoc
reflection. The second Wynn case reached H_init, routing, a shared soft-Signal initial
and correction, and H_reflect initial and correction—the deepest ordinary Fast
trajectory so far.

Exact persisted content exposed two independent semantic failures. The
`guidance_acceleration` correction cited a December 2022 Encore Boston Harbor
sale-leaseback (`$1.70 billion` proceeds, `$182 million` gain, `$1.51 billion` lease
liability) as positive current guidance even though no cited text named guidance,
outlook, forecast, or a management expectation. H_reflect then copied that false
Signal into a 678-character claim. The parser's 400-character maximum was absent from
the system output contract, and its correction feedback named no field or linked
belief, so the model repeated the invalid state byte-for-byte.

Signal versions may now own `result_required_evidence_phrases`; a non-unavailable
result must cite at least one measured-object phrase or correct to canonical
`unavailable`. `guidance_acceleration:v1` carries explicit guidance/outlook/forecast/
management-expectation phrases, while the real `$1,500 per ounce` guidance clause
still passes. Every ResearchState prompt now exposes the 1-400 claim bound, and raw
prevalidation aggregates exact `supporting_evidence[index].claim` paths, actual
lengths, and identical belief/contradiction paths before the sole correction. Direct
replay of v69's actual artifacts now rejects the sale-leaseback Signal and reports
`supporting_evidence[1].claim length=678` plus `current_beliefs[1]`. All 463 repository
tests and lint pass. The successor contract must freeze 175 attempts, `$18.11296800`,
and 764 data requests; v69 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v68 contract
`9a70a62...421bb` rejected its only candidate after the first case at authoritative
pointers `round=0/cycle=0`. It used 16 attempts, `$0.02271920`, and three locally
denied SEC request-ledger entries. The v67 repair passed its paid boundary: a
30,830-character guidance projection sent both initial and correction calls, the
correction moved from a truncated `$1,` edge to the complete `$1,500 per ounce`
clause, and H_reflect removed the answered guidance need. A four-Signal deterministic
round then preserved state correctly when three results were unavailable and the
only available negative-word count was neutral.

The third routing response selected one relevant financing Signal plus an irrelevant
`customer_concentration` analogy for gold-price profitability. Its budget-trimmed
14,739-character shared context sent the initial call. Financing returned a separately
valid completed-share-sale result, while customer concentration inferred diversified
customers from silence and changed the case of four purported literal quotes. The
old mapper reported only `must map uniquely`; its 26,765-byte correction request then
exceeded the remaining budget, and the whole soft subgroup was discarded, including
the valid financing sibling. `customer_concentration:v1` now requires a pre-existing
customer/client/buyer/offtake/backlog/order/program object before routing. Literal
mapping feedback now names the evidence index, supplied projection, supplied/visible
occurrences, and matching ids. If an initial shared call has accepted siblings but a
pending correction cannot pass preflight, only the pending rows become canonical
`unavailable`; accepted results and paid usage survive for ordinary H_reflect. All
460 repository tests and lint pass. The successor contract must freeze 187 attempts,
`$18.12799812`, and 767 data requests; v68 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v67 contract
`47d64a8...d364` rejected its only candidate after the first case at authoritative
pointers `round=0/cycle=0`. It used eight attempts, `$0.01462384`, and three SEC
request-ledger entries. H_init's initial UBS claim added an absent `$20` comparison;
its exact correction removed only that quantity. Routing initially repeated the v66
mature-project commercialization error, then its exact correction removed that ref
and retained the valid guidance selection, live-verifying the new applicability gate.

The selected guidance batch still made zero provider calls. Its persisted exact body
was 43,839 bytes plus a 4,000-token output reservation, while only 41,766 adaptive
tokens remained after H_init/routing and the frozen terminal reserve. The 30,830-
character projection therefore failed the conservative byte-for-token preflight;
Predictor/post-hoc completed, but the unchanged `continue` state remained correctly
ineligible. Soft-Signal projection is now budget-aware only when the complete bounded
request cannot fit: exact provider-body estimation preserves one highest-ranked
projection per selected Signal when feasible, then adds further ranked projections
while the whole request fits. Complete Raw Info, per-Signal projection scope, literal
mapping, validation, and the unchanged correction context remain intact. Exact v67
replay retains 15/19 projections and the complete `$1,500 per ounce` guidance clause,
with a 41,101 reservation under the 41,766 limit. All 458 repository tests and lint
pass. The successor contract must freeze 203 attempts, `$18.15071732`, and 770 data
requests; v67 remains immutable evidence.

Current ordinary-loop repair (2026-08-30): immutable v66 contract
`784b5eb...65bc5` rejected its only candidate on the first H_reflect correction at
authoritative pointers `round=0/cycle=0`. It used seven completed attempts,
`$0.01124816`, and three SEC request-ledger entries. H_init again passed in one call
with a literal two-row market claim and one unresolved guidance/project need. Routing
correctly marked guidance as `answer_need`; the soft batch's initial guidance quote
ended at `$1,`, and its correction moved to the overlapping projection containing the
complete `$1,500` clause. This live-verifies the projection-edge correction path.

The initial reflection then added an unsupported `2025` to the Signal claim and kept
the exact compound guidance/project need. Its aggregated error correctly named the
claim, linked belief, invalid needs field, index, and original value. Nevertheless,
correction returned the exact same ResearchState. Exact request inspection found a
contract contradiction: H_reflect's correction system said to act when
`validation_feedback` was non-null, but the actual user payload contained only
top-level `invalid_output` and `validation_error`; the named trigger field did not
exist. Provider usage also hit only 640 of 2,883 correction input tokens.

H_reflect now uses the stable correction transport already used by H_init/routing:
byte-identical system prompts, complete unchanged reflection context, and one final
`validation_feedback` field that is null initially and contains the rejected state
plus aggregated error on correction. Exact v66 replay confirms the new payload and a
minimal corrected state passes. The same routing output also treated Tasiast and
Lobo-Marte mature mining projects as product commercialization, then paid for an
LLM Signal to return unavailable. `commercialization_status:v1` now requires existing
product/technology/prototype/commercialization wording, while real prototype-product
needs remain routable. All 457 repository tests and lint pass.

Before the successor contract, the remaining frozen ceilings are 211 attempts,
`$18.16534116`, and 773 data requests; v66 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-30): immutable v65 contract
`2568710...76a4` rejected its only candidate on the first H_reflect correction at
authoritative pointers `round=0/cycle=0`. It used six completed attempts,
`$0.00529704`, and three SEC request-ledger entries. Exact inspection covered the
complete proposer, H_init, routing, soft-Signal, H_reflect, and correction
requests/responses. The v64 repair passed its paid check: H_init required one call,
used only literal quantities, and returned two source-backed divestiture facts plus
one information need without temporal-metadata leakage.

Routing reasonably selected `financing_listing_action:v1` and a deterministic cash
context. The soft result literally confirmed the completed Asante share sale; cash
was honestly unavailable. The initial reflection adopted the available evidence but
retained its compound need for transaction terms, closing dates, and proceeds use.
Only the sale terms were partly answered, so the logically correct transition was to
narrow the need to the two unresolved facets. The old correction error stated only
that the need set must change, while the shared correction contract required every
named field/item to change; it did not identify one exact field or indexed value, and
the model returned the same output byte-for-byte.

H_reflect feedback now names `invalid_field='next_information_needs'` and supplies
every retained indexed value, while explicitly requiring only an evidence-supported
removal/narrowing and byte-for-byte preservation of unanswered items. The router may
use `answer_need` only for a facet directly covered by the card description and may
not promise coverage of other facets; contextual cards use another accurate reason.
H_init now asks only for facts absent from Basic Info and its returned state, and
partly answered compound questions retain only unresolved facets. Exact v65 replay
rejects the persisted no-op and accepts a split into closing-date and proceeds-use
needs. All 455 repository tests and lint pass.

Before the successor contract, the remaining frozen ceilings are 218 attempts,
`$18.17658932`, and 776 data requests; v65 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-30): immutable v64 contract
`04fe683...8390` rejected its only candidate on the first H_init correction at
authoritative pointers `round=0/cycle=0`. It used three completed attempts,
`$0.00808780`, and three SEC request-ledger entries. The proposer passed in one
cache-heavy call and made the required attributable change: it retained the compact
market backbone, added a bounded earnings-call request, and expanded H_init's
expectation-gap instruction without changing Predictor semantics. The complete
proposer request/response and both H_init requests/responses were inspected.

The initial ResearchState contained two otherwise grounded transcript claims that
added `2025` to `Q2`/`Q3` even though their exact quoted spans contained only the
quarter labels, plus two other quantitative beliefs that paraphrased rather than
copied their evidence claims. The old prevalidator reported only the two missing-year
claims and linked beliefs. The 10,624/11,899-token-cache-hit correction fixed the two
unreported belief links but preserved every explicitly rejected `2025`, so validation
failed again. This repeats v62's temporal-metadata pattern and shows that sequentially
exposing locally decidable defects wastes the sole correction.

The initial role instruction now states that a year, quarter number, date, or other
temporal quantity cannot be borrowed from projection metadata, neighboring text, or
general document context. Before correction, raw validation aggregates every
decidable missing quantity and quantitative assertion-link path. Correction also
states the minimal safe repair: delete each listed absent quantity from the named
claim and linked assertion unless a same-claim literal containing it is added. It
still never rewrites evidence locally. The persisted v64 invalid state replays to all
six exact paths, and a minimal corrected form passes. All 455 repository tests and
lint pass.

Before the successor contract, the remaining frozen ceilings are 224 attempts,
`$18.18188636`, and 779 data requests; v64 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-29): immutable v63 contract
`8d43153...01e1` rejected its only candidate after one otherwise complete and
correctly judged case at authoritative pointers `round=0/cycle=0`. It used 11
completed attempts, `$0.01701224`, and three SEC request-ledger entries. Exact
inspection covered proposer, H_init initial/correction, both routing decisions, the
soft-Signal initial/correction, H_reflect initial/correction, both deterministic
Signal results, Predictor, and post-hoc. Precise correction feedback worked live:
H_init removed only an unsupported date, the soft Signal replaced a projection-edge
`$1,` quote with the complete `$1,500` clause, and H_reflect removed only the need
that its adopted `answer_need` guidance evidence had answered.

The second routing response then relabeled an Asante equity sale as a customer order
and selected `order_quality:v1`; its actual Signal request was persisted but refused
before transmission by the conservative budget reservation. The completed
`gross_margin_change` and `revenue_acceleration` results were both honestly
`unavailable`. Runtime evaluated the generic all-unavailable shortcut before the
partial soft-refusal terminal rule, skipped the required H_reflect call, left
`decision=continue`, and excluded the case despite a complete correct Predictor and
post-hoc result.

Signal versions may now own a finite `routing_required_research_phrases` gate.
`order_quality:v1` requires existing purchase-order, customer-order, backlog,
contract-award, or customer-commitment wording in accepted research context; a new
analogy invented only in routing prose cannot satisfy it. When a soft request is
refused after an all-unavailable deterministic partial batch, runtime now performs
one terminal H_reflect call, and validation requires every prior field and item to
remain byte-for-byte while only `decision` changes to `finalize`. Both constraints
pass exact v63 artifact replay, all 454 repository tests, and lint.

Before the successor contract, the remaining frozen ceilings are 227 attempts,
`$18.18997416`, and 782 data requests; v63 remains immutable evidence and cannot
resume across the code revision.

Current ordinary-loop repair (2026-08-28): immutable v62 contract
`fe5027b...a28d2c` rejected its only candidate on the first H_init case at
authoritative pointers `round=0/cycle=0`. It used four attempts, including one
zero-cost sandbox-denied HTTP attempt, `$0.00785680`, and three SEC request-ledger
entries. The proposer passed in one call with a 1,152/1,158-token cache hit and
returned a market/news/earnings-call Plan whose four actual role fields preserve the
fixed Predictor boundary. H_init then used 11,103 input tokens; its only local defect
was `supporting_evidence[2]` claiming `Q2 2025` while the exact quote said only
`second quarter`. The correction had an 11,008/11,941-token cache hit but returned
the identical ResearchState byte-for-byte and failed again.

Exact correction-context inspection found that a local semantic `ValidationError`
was wrapped twice as `invalid JSON fields` containing every ResearchState key, while
the role instruction required every named field to change. The raw quantity
prevalidator also named only the evidence ref, not its identical quantitative belief.
Semantic errors now pass through unchanged; quantity feedback names both the exact
evidence index and every linked belief/contradiction index, and correction preserves
unrelated valid content byte-for-byte. The persisted v62 response replays to the new
precise error: `supporting_evidence[2]`, missing `2025`, linked
`current_beliefs[1]`.

All 450 repository tests and lint pass. Before the successor contract, the remaining
frozen ceilings are 238 attempts, `$18.20698640`, and 785 data requests; v62 remains
immutable evidence and cannot resume across the code revision.

Current ordinary-loop repair (2026-08-28): immutable v61 contract
`1efbf49...88efa` reached one complete real case, then rejected the only candidate
at authoritative pointers `round=0/cycle=0`. It used 11 completed model attempts,
`$0.01205232`, and five SEC request-ledger entries. Exact inspection covered both
proposer attempts/corrections, H_init, three routing decisions, deterministic Signal
results, Predictor, and post-hoc. Every selected deterministic Signal returned honest
`unavailable`; H_reflect correctly used zero calls. The final routing decision was
empty, but runtime left the unchanged `continue` state and excluded the otherwise
complete case as `unfinalized_case`.

An empty selection or exhausted eligible Registry now represents natural evidence-
collection closure, not a claim that uncertainty was resolved. Runtime copies the
complete last ResearchState, changes only `decision=continue` to `decision=finalize`,
asserts every other field remains equal, and preserves
`termination_trigger=no_signal_match`. All-unavailable batches still skip H_reflect;
cost/round/call exhaustion without a reflectable terminal batch remains ineligible
and cannot use this rule.

All 449 repository tests and lint pass. Before the successor contract, the remaining
frozen ceilings are 242 attempts, `$18.21484320`, and 788 data requests; v61 remains
immutable evidence and cannot resume across the code revision.

Current ordinary-loop repair (2026-08-28): immutable v60 contract
`ae7b3a9...2c9e9` reached the first complete real case, then rejected the only
candidate at authoritative pointers `round=0/cycle=0`. It used 15 completed model
attempts, `$0.01937908`, and four SEC company-facts request-ledger entries. Exact
inspection covered proposer, H_init, three routing/reflection rounds, soft-Signal
initial/correction, Predictor, and post-hoc payloads/responses. The first reflection
adopted available `guidance_acceleration` evidence selected specifically to answer the
production/cost need, yet retained all five needs unchanged. On the third round a
soft-Signal request could not pass conservative pre-send reservation after four
deterministic results had completed; H_reflect again returned `continue`, the fixed
Predictor and post-hoc still completed, and the trajectory was excluded as
`unfinalized_case`.

H_reflect now receives exact executed selection intents. A continuing state that
adopts evidence from an available `answer_need` selection must remove or genuinely
narrow at least one need instead of returning the same set. The last reflectable
batch also receives an exact terminal directive for round/call exhaustion or a
pre-send soft-Signal budget refusal; the model must author `finalize` while it may
retain unresolved needs/open questions. One correction remains available, and
runtime never mutates the decision. The v60 states replay directly into both new
validation errors. The financial-statements Basic request was also audited: its local
SEC-derived `financials` document was seven days outside the Plan's 180-day lookback,
so the unresolved acquisition is a real coverage gap rather than a source-alias bug.

All 449 repository tests and lint pass. Before the successor contract, the remaining
frozen ceilings are 253 attempts, `$18.22689552`, and 793 data requests; v60 remains
immutable evidence and cannot resume across the code revision.

Current Slow-bootstrap handoff (2026-08-28): immutable v59 contract `60287299...2ad8` committed cycle 1 at authoritative pointers `round=0/cycle=1` after one H1 attempt, `$0.00101332`, twelve provider requests (two SEC profiles and ten SEC company-facts fetches), and no Registry change. H1 passed in one call with a 2,432/2,521-token cache hit. H2 deterministically shortlisted 12 refs for each hypothesis and used zero calls. The relaxed full-document rule admitted strong near-complete packets, then the exact model-excerpt recomputation rejected every case because only one or two terms survived the 1,200-character window; H3 and Update therefore correctly used zero calls. This live-verifies that the new threshold improves retrieval reach without bypassing the visible-evidence boundary. A second invocation made no requests/calls and was rejected because `slow_bootstrap` is intentionally single-cycle, so E1/E2 cycle 3 cannot be tested in bootstrap mode.

No additional code change follows v59. The remaining work moves to an ordinary `fast_then_slow` contract so newly committed Fast learning can drive Update and repeated cycles can reach exploration. Under the frozen remaining attempt ceiling, the verification contract will use one full 24-case candidate per Fast round rather than three parallel candidates; this preserves the complete per-case Signal/evidence/learning path being tested while fitting at least two cycles needed for Update.

V59 leaves 268 attempts, `$18.24627460`, and 797 data requests. The repository remains at the 447-test/lint-passing `07e20ab` checkpoint with no task-file changes beyond this recorded handoff.

Current Slow-bootstrap handoff (2026-08-28): immutable v58 contract `512d16da...d8fd` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00253764`, two SEC profile requests, and no Registry change. Initial validation rejected three feature-bearing group definitions plus one alternate `underperform` outcome; correction produced three valid fixed-group hypotheses. H2 deterministically shortlisted 12 refs for each with zero calls. H3 then used zero calls because no hypothesis had two positive and two control cases passing query coverage, and Update correctly used zero calls. Exact resolution inspection showed many otherwise relevant filings at 4/5 terms plus an ordered pair for production/consensus or 3/4 plus `revenue growth` for composition, but the all-terms packet rule discarded them before the bounded excerpt could be assessed. This treated abstract query modifiers such as `comparison` and `trajectory` as mandatory Boolean terms rather than retrieval vocabulary.

H3 query coverage now requires all terms for one/two-term topics and a rounded-up 75-percent supermajority for longer topics, always with at least one short-range consecutive query pair when more than two terms exist. The exact v54 false-feasibility pattern remains rejected: its visible excerpts had only 3/6 terms or no ordered pair, below the new 5/6 requirement. The same threshold is recomputed over exact masked excerpts after projection.

Verification for strong-supermajority H3 coverage: all 447 repository tests and lint pass, including 4/5 acceptance and 3/6 rejection. V58 used two attempts and two provider requests, so the next fresh ceiling is 269 attempts, `$18.24728792`, and 809 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v57 contract `c6221179...39b9` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00238112`, two SEC profile requests, and no Registry change. Initial validation correctly rejected three feature-bearing `Discovery group: issuers with ...` parentheticals. Correction rewrote all three to the feature-free alias `positive/control cases (fixed Discovery group)`, but the same-label whitelist was still overly literal and rejected that finite alias before H2. Exact replay of the persisted correction now accepts all three hypotheses under the repaired parser; no resampling was used to establish the fix.

H1 now accepts exactly two feature-free alias families: the same explicit Discovery label and `(fixed Discovery group)` attached to an already positive/control-labeled prefix. Any feature/result/issuer condition, colon payload, or opposite label remains a redefinition failure. The item-local correction instruction from v56 remains active.

Verification for finite fixed-group aliases: all 446 repository tests and lint pass, and the exact v57 correction response replays with all three ids accepted. V57 used two attempts and two provider requests, so the next fresh ceiling is 271 attempts, `$18.24982556`, and 811 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v56 contract `7513df44...b6fb` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00194404`, two SEC profile requests, and no Registry change. The initial cached-prefix response produced three grounded hypotheses; only `revenue_beat_prior_quarter` was rejected as a restatement of an existing stable revenue-growth construct. The other production-guidance and analyst-revision hypotheses were not named by validation. The correction nevertheless returned only `{"hypotheses":[]}`, so the nonempty-demand guard correctly failed it, but the whole portfolio lost two independent valid items and H2/H3 did not run. Update again correctly used zero calls.

H1 correction now explicitly preserves every hypothesis id not named by the aggregated validation error byte-for-byte, changes/removes only named invalid items, and forbids using an empty correction to erase unaffected work when demand is nonempty. This retains the one bounded correction and all local semantic gates while preventing one bad portfolio item from creating an all-or-nothing failure.

Verification for item-local H1 correction instructions: all 445 repository tests pass and repository lint passes. V56 used two attempts and two provider requests, so the next fresh ceiling is 273 attempts, `$18.25220668`, and 813 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v55 contract `1a20af5a...8f00` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two H1 attempts, `$0.00212716`, four SEC profile request-ledger entries, and no Registry change. The initial response repeated three circular parenthetical definitions and one `subsequent quarters` target; the single correction received one aggregated safe error with a 2,432/3,085-token cache hit and removed every candidate-specific definition/future horizon. It then used `positive cases (the Discovery positive group)` and the analogous control alias. The over-broad parentheses guard rejected these unchanged-label aliases before H2, although they do not redefine membership. Exact replay against the repaired parser accepts all three correction hypotheses in one call. H2/H3 were therefore not reached in the immutable v55 run, and Update correctly used zero calls.

The H1 guard now distinguishes an exact same-label Discovery alias from a feature-bearing or cross-label parenthetical. Membership clauses and candidate-specific parentheses remain invalid; only `positive/control cases|groups|cohorts (the Discovery same-label cases|groups|cohorts)` pass. This is a semantic narrowing of the false positive, not a relaxation of the frozen-label boundary.

Verification for same-group alias handling: all 445 repository tests pass with the bundled Python 3.12 runtime; repository lint passes, and the exact v55 correction response replays as accepted. V55 used two attempts and four provider request-ledger entries, so the next fresh ceiling is 275 attempts, `$18.25415072`, and 815 data requests.

Current Slow-bootstrap handoff (2026-08-28): immutable v54 contract `d47242d5...5735` committed cycle 1 at authoritative pointers `round=0/cycle=1` after two paid attempts, `$0.00216916`, four SEC profile request-ledger entries across preflight/execution, and no Registry change. Exact H1/H3 wire requests, responses, token usage, anonymous H2 briefs/rankings, all model-visible evidence excerpts, Raw Info resolution audits, ledgers, transition, and Locked-Test flag were inspected. H1 returned three hypotheses and deterministic H2 used zero calls. Two hypotheses lacked enough point-in-time cases; the revenue-composition hypothesis reached H3, whose correct `inconclusive` response noted that the visible excerpts contained only unrelated operating/risk/filer prose. The controller had nevertheless labeled those packets sufficient using terms found only across the hidden full document: none of the four exact 1,200-character model excerpts retained the complete six-term query, and `composition` was absent from all four. The H1 response also redefined frozen group membership with `positive/control cases are issuers ... as/that ...`, which the prior parentheses-only guard missed.

H1 now rejects both parenthetical and membership-clause group redefinitions and tells the correction to express a feature difference between already frozen groups. H3 now recomputes the same distinct-term and short-range-pair coverage over the exact identity-masked excerpts after projection; hidden full-document coverage remains audit-only, and an insufficient visible packet becomes local evidence-unavailable before a model call. This removes the exact v54 false-feasibility call without weakening semantic `inconclusive`, source lineage, or point-in-time checks.

Verification for membership-bound H1 and model-visible H3 coverage: all 444 repository tests pass with the bundled Python 3.12 runtime; repository lint passes. V54 used two attempts and four provider request-ledger entries, so the next fresh ceiling is 277 attempts, `$18.25627788`, and 819 data requests. A fresh frozen contract is required to live-validate H1 correction and visible-excerpt gating; ordinary Fast-derived learning remains required to exercise Update.

Current Slow-bootstrap handoff (2026-08-28): immutable v53 contract `4212dbe3...e6e6` committed cycle 1 at authoritative pointers `round=0/cycle=1` after one paid H1 attempt, `$0.00068292`, four successful SEC profile requests across preflight/execution, and no Registry change. Exact H1 wire prompt, actual field inventory, response, cache usage, local result, ledgers, transition, and Locked-Test flag were inspected. The 2,425-input-token call had a 2,304-token cache hit but returned only `{"hypotheses":[]}` in seven output tokens. H2 correctly used zero calls but had no hypothesis to shortlist, so H3 and Update were not called. The reasonless empty portfolio contradicted the same nonempty four-item Fast backlog that produced valid canonical candidates in v52 and did not establish demand exhaustion.

H1 retains the fixed positive/control target, alternate-horizon rejection, id/query-scoped duplicate boundary, aggregated feedback, stable correction prefix, standalone `P(` rule, `yoy` identity preservation, case/group/cohort synonyms, no invented refs, no short-window market outcomes, no data-readiness statements, no raw absolute cross-issuer scale, no fixed-group redefinition, group-level falsifiers, and concise two-to-eight-term retrieval topics. The controller constructs the bounded anonymous H2 briefs before H1 and publishes only their actually present optional fields and categorical values. H1 `applicability` is one machine-checkable, non-conjunctive rule: all ready issuers, bounded business-description topics, or one observed industry/sector/exchange/size/listing-age/Raw-Info-source rule. Free prose, absent values, and hidden document prerequisites are rejected together; profile shortage consumes zero H1 tokens. When real `signal_need_items` are nonempty, H1 must return at least one grounded hypothesis; a reasonless empty portfolio is valid only when the demand list is empty. H2 is a deterministic local shortlist over that exact rule, preserving bounded brief order without a model prompt, quote/reason schema, or correction. H3 retains hidden-body removal, complete ordered query coverage, and distinct inconclusive/evidence-unavailable state.

Verification for demand-bound nonempty H1: all 442 repository tests pass with the bundled Python 3.12 runtime; repository lint passes. V53 used one attempt and four provider requests, so the next fresh ceiling is 279 attempts, `$18.25844704`, and 823 data requests. A fresh frozen contract is required to live-validate empty correction, zero-call H2, and reach H3; ordinary Fast-derived learning remains required to exercise Update.

Current v23 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v23` froze exact contract `5bc1b988...cbc03` at code revision `7872ddf`, reached the first proposer approval boundary, and transmitted zero LLM requests at authoritative pointers `round=0/cycle=0`; Locked Test remained sealed. Its exact 5,859-byte proposer body was inspected and contained only the fixed prior, one committed historical seed, empty meta-info, source enum, and attributable Plan-change constraint. Readiness used three real SEC requests. A cross-request audit of v22 then isolated the largest avoidable correction cost: a 38.5k-character shared soft-Signal projection was correctly sent only once per batch, but the correction changed its system prompt and therefore received only 384-512 cache-hit tokens while repeating roughly 12k input tokens. Initial/correction Signal calls now use one byte-identical conditional system prompt, keep a stable full `batch_signal_refs`, and append only dynamic `validation_feedback` after the unchanged projection. No context, Signal skill/spec, evidence, or local validation was removed; conservative reserves remain cache-miss priced. The v23 contract cannot resume after this code change. The next contract must freeze 521 attempts, `$18.58031964`, and 921 real provider requests; v23 and earlier workspaces remain immutable evidence.

Verification for the soft-Signal correction-prefix repair: all 384 repository tests and lint pass.

Current v22 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v22` ended normally at authoritative pointers `round=0/cycle=0` after 28 attempts (26 completed plus two paid malformed-JSON failures), `109,548` input / `15,804` output tokens, `$0.03952368` settled cost, and four real SEC requests. All three candidates reached the first case and failed during H_reflect. Exact responses proved that adopting evidence is not equivalent to answering every active need: one response newly resolved production/cost guidance while retaining that same need, while two other responses correctly retained broad catalyst or gold-price questions that their new company-price/news evidence did not answer. The old blanket progress gate therefore both missed an internal stale need and forced unrelated unanswered needs to change. Exact unanswered needs may now remain byte-for-byte, changed needs retaining at least 90% of an old need remain invalid, and a newly resolved question sharing an ordered three-content-word phrase with an exact retained need fails closed. Unavailable Signal belief/resolution drift is enforced independently, and directly decidable Signal-quantity plus need-transition errors share the one correction. The next contract must freeze 521 attempts, `$18.58031964`, and 924 real provider requests; v22 and earlier workspaces remain immutable evidence.

Verification for the v22 reflection-state separation: all 384 repository tests and lint pass.

Current v21 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v21` was intentionally interrupted at authoritative pointers `round=0/cycle=0` after 34 reserved attempts (32 completed, one paid malformed-JSON failure, and one conservatively retained interruption), `$0.03687852` settled cost, a `$0.00471660` interrupted reservation, and three real SEC fetches. The new commercialization boundary worked on the actual mature-mining batch, returning `unavailable`, and H_reflect wire bodies fell to 6.8-9.4k bytes without canonical document ids/hashes/raw spans. Exact responses nevertheless exposed three logical defects: an unavailable customer-concentration interpretation became a false absence belief and resolved question; the only reflection correction embedded the entire prior need in a longer “given the absence...” sentence; and another selector returned an empty batch for an explicit production/cost `guidance` need. Every downstream model view now canonicalizes unavailable as coverage-only, same-or-larger need lists reject a new need retaining at least 90% of a prior need's word set, and version-owned `routing_need_phrases` trigger one empty-selection correction without local Signal choice. The next contract must freeze 549 attempts, `$18.61984332`, and 928 real provider requests; v21 and earlier workspaces remain immutable evidence.

Verification for the v21 semantic-state and routing repair: all 383 repository tests and lint pass.

Current v20 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v20` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 41 settled attempts (40 completed plus one paid malformed-JSON failure), `$0.05078472` actual cost, and three real SEC fetches. Every one of its seven actual `H_reflect` calls adopted new Signal evidence while returning the exact same information needs and never resolving a question; the role also received canonical long `exact_span` payloads with transcript/market serialization noise. One initialization response contained five missing evidence kinds plus three already-visible unsupported quantities, but sequential validation exposed only the first layer before the sole correction. A soft Signal response also classified ordinary mature-mine production as a positive product-commercialization transition. H_reflect now receives an 8k bounded normalized evidence view and must make a substantive state transition after adopting evidence; one correction aggregates all decidable tagged-ref/Basic-quantity errors; and the seed commercialization card/skill explicitly excludes routine mature operations. The next contract must freeze 583 attempts, `$18.66143844`, and 931 real provider requests; v20 and earlier workspaces remain immutable evidence.

Verification for the v20 adaptive-context, layered-correction, and Signal-applicability repair: all 380 repository tests and lint pass.

Current v19 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v19` was intentionally stopped at authoritative pointers `round=0/cycle=0` after seven reserved attempts (six completed plus one conservatively retained interruption), `$0.00792036` settled cost, a `$0.00322868` interrupted reservation, and two real provider fetches. Its second actual proposer response copied all three output-contract placeholders—`complete initialization instructions`, `complete reflection instructions`, and `complete final analysis instructions`—and runtime accepted that non-executable Plan because the strings were non-empty and differed from the parent. The output example now contains logically complete role instructions, exact example echoes and generic placeholders are rejected, and every proposed `H_*` field must cover its role-specific semantics before parent/focus comparison. Correction feedback names every field that must change and rejects an unchanged replay. The next contract must freeze 624 attempts, `$18.71222316`, and 934 real provider requests; v19 and earlier workspaces remain immutable evidence.

Verification for the v19 Plan-content repair: all 377 repository tests and lint pass.

Current v18 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v18` ended normally at authoritative pointers `round=0/cycle=0` after 29 attempts (27 completed plus two paid malformed-JSON failures), `$0.04007276` settled cost, and three real provider fetches. Its deepest candidate reached two Signal rounds, revealing that the 2025 Wynn case was incorrectly using 2017/2018 `Revenues` facts even though current 2024/2025 facts existed under `RevenueFromContractWithCustomerIncludingAssessedTax`; H_reflect then described the stale result as positive operational performance. The financial parser now recognizes both assessed-tax revenue aliases and makes any current period older than 550 days `unavailable`. Exact replay selects 2025-Q1 revenue growth `-0.0872356` and operating-cash-flow margin `0.0786722`, not the old 2018 values. Reflected claims may copy a deterministic Signal's exact canonical numeric interpretation, but still reject rounded percentages or extra raw quantities. `H_init` also stops asking for runtime-owned evaluation baseline dates/prices. The next contract must freeze 631 attempts, `$18.72337220`, and 936 real provider requests; v18 and earlier workspaces remain immutable evidence.

Verification for the v18 current-period and derived-claim repair: all 376 repository tests and lint pass.

Current v17 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v17` ended normally at authoritative pointers `round=0/cycle=0` after 11 attempts (10 completed and one retryable SSL failure), `$0.01099476` settled cost, and two real provider fetches. The first candidate's actual routing response selected four relevant Signals, but copied the visible card categories `catalysts`, `risks`, and `product` into `context_tags`; those values are absent from the frozen context-tag enum, the correction repeated them, and runtime rejected the candidate before executing any Signal. Auxiliary routing tags now follow the intended local non-semantic path: normalize, deduplicate, drop unknown values, and retain at most four; wrong refs, missing fields, and invalid reason/role enums still correct once and fail closed. The other two candidates independently failed the unchanged quantitative citation gate. The next contract must freeze 660 attempts, `$18.76344496`, and 939 real provider requests; v17 and earlier workspaces remain immutable evidence.

Verification for the v17 tag-normalization repair: all 374 repository tests and lint pass.

Current v16 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v16` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 15 reserved attempts (14 completed plus one conservatively retained interruption), `$0.01329608` settled cost, a `$0.00543816` interrupted reservation, and three real provider fetches. The first actual routing request named latest quarterly revenue and operating cash flow as an information need and exposed the unexecuted `operating_cash_flow_margin:v1`, `revenue_growth_yoy:v1`, and `revenue_acceleration:v1` cards, yet the model returned an empty batch and runtime prematurely finalized research. Empty routing now receives one semantic correction only when a need repeats an exact three-or-more-word phrase from an available Signal ref; unmatched empty remains valid, fuzzy/single-word matching is forbidden, and runtime never selects a Signal locally. The next contract must freeze 671 attempts, `$18.77443972`, and 941 real provider requests; v16 and earlier workspaces remain immutable evidence.

Verification for the v16 routing repair: all 373 repository tests and lint pass.

Current v15 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v15` ended normally at authoritative pointers `round=0/cycle=0` after 40 completed attempts (`110,543` input / `16,595` output tokens, `$0.04024524`) and three real provider fetches. Three accepted Plans all failed closed during initialization: one SEC table literal was genuinely ambiguous because it occurred twice; two other responses exposed a context-usability defect by constructing shortened market JSON citations and repeating the same rejected provenance after correction. The exact Life Time request also showed `H_init` treating the fixed six-month doubling evaluation outcome as if it were an issuer target whose terms should be researched. The role prompt now states that this is an evaluation definition, requires complete visible market rows, and makes clear that a correction must replace or remove every rejected item without any local evidence repair. The next contract must freeze 686 attempts, `$18.79317396`, and 944 real provider requests; v15 and earlier workspaces remain immutable evidence.

Verification for the v15 prompt/context repair: all 372 repository tests and lint pass.

Current v14 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v14` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 14 reserved attempts (13 completed plus one conservatively retained interruption) and two real SEC fetches. Candidate c01 was incorrectly rejected because its exact SEC facts `1605300000`/`2446400000` were reasonably expressed as `$1.6053 billion`/`$2.4464 billion`; numeric support now treats each explicitly unit-qualified token's unscaled and exactly Decimal-scaled values as alternatives, never as rounded approximations. This preserves the prior legitimate `2,521,793 thousand` literal match while accepting exact raw-unit conversion. c02 then produced two useful correct-case decision drivers, but the fixed-semantics scanner wasted a correction on the descriptive phrase “far below the doubling threshold”; bare threshold/cutoff references are now allowed, while set/use/change actions, explicit replacement numeric thresholds, probabilities, and odds remain blocked. The next contract must freeze 726 attempts, `$18.83341920`, and 947 real provider requests; v14 and earlier workspaces remain immutable evidence.

Verification for the v14 repairs: all 371 repository tests and lint pass.

Current v13 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v13` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 16 reserved attempts (15 completed plus one conservatively retained interruption) and two real SEC fetches. Its first soft-Signal response quoted the complete `$1,500` guidance sentence but attached the neighboring truncated projection id: that id contained the quote zero times, while the full visible projection set contained it exactly once under `projection_a3f27...`. The old Signal mapper rejected it, spent its sole correction, then lost valid guidance when the correction was malformed. Signal evidence now follows the existing Basic-ref rule: a wrong/unknown projection id is deterministically relocated only when the unchanged exact quote has one total visible occurrence; zero/multiple matches still fail closed, and internal-edge checks run on the resolved projection. v13 also live-verified that correct post-hoc output now retains three concrete decision drivers and that later H_reflect preserved the earlier Signal claim. 369 repository tests and lint pass. The next contract must freeze 740 attempts, `$18.86772452`, and 949 real provider requests; v13 and earlier workspaces remain immutable evidence.

Current v12 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v12` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 23 reserved attempts (22 completed plus one conservatively retained interruption) and two real SEC fetches. Exact first-case artifacts exposed a cross-layer evidence loss: the soft-Signal batch cited Paracatu 585,000 ounces/Tasiast 119,000 ounces and a guidance literal ending at the internal projection boundary `$1,`, but H_reflect rewrote them as unsupported 513,000-ounce/$2,200 and $1,400 claims; the full overlapping projection actually said $1,500. Current-batch Signal claims now require all quantities in their exact referenced evidence, retained older Signal claims are immutable when their backing batch is no longer visible, and internal projection-edge citations fail closed in favor of a complete overlapping clause. Exact post-hoc payloads also proved its Basic source index was silently empty because the compactor misread an already-compact Predictor view, and every framework-correct response returned an all-empty reflection despite explicit guidance; the source index now survives without restoring full Basic text, and correct post-hoc output requires a concrete `decision_drivers` item. Finally, Wynn-branded property names survived Predictor masking because the distinctive four-letter leading brand was excluded; non-generic four-letter brands are now masked and scanned. 368 repository tests pass. The next contract must freeze the remaining extension ceilings of 756 attempts, `$18.89346688`, and 951 real provider requests. v12 and earlier workspaces remain immutable evidence.

Current v11 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v11` was intentionally stopped at authoritative pointers `round=0/cycle=0` after 14 attempts and three real SEC fetches. The first case completed in seven model calls with deterministic terminal closure; provider usage proved real cache reuse, including 1,024/1,047 input tokens on each proposer and 9,984/10,036 on a soft-Signal batch. The second case exposed that a `10-q` Basic request ranked/chunked raw SEC markup before projection: its model view contained 12 HTML/XBRL tags, seven `style=` fragments, and 10,064 quarterly characters, while one accepted literal claim combined an ending cash balance absent from its cited span. Full-document readable-text ranking now maps selected windows back to exact raw offsets, removes complete and boundary-fragment tags, decodes single-character HTML entities, and enforces numeric claim support across same-claim Basic refs. Exact v11 replay produces zero tags/style/XBRL/entities and reduces the Basic payload from 22,610 to 17,548 characters while retaining the relevant cash/debt prose. 362 repository tests pass; the next contract must freeze the remaining extension ceilings of 779 attempts, `$18.91672256`, and 953 real provider requests. The v10 and earlier paragraphs below are immutable historical handoff context.

Current v10 continuation (2026-08-23): immutable workspace `deepseek-v6-context-remediation-20260823-v10` froze exact contract `010d3aa0...f20db` with 800 newly authorized attempts, `$18.93681116` remaining cumulative cost, and 958 remaining provider requests. It was intentionally interrupted after seven reserved attempts and two real SEC fetches at authoritative pointers `round=0/cycle=0`. Exact responses proved that fixed-semantics scanning misclassified “without calculating probabilities” as affirmative drift and that an accepted Plan ignored its deterministic `B/H_init` change focus by changing only `H_analyse`; Responses-style nested cache usage was also invisible. The owning specs and runtime now distinguish explicit negative guardrails, report the actual prohibited match, enforce the named focus against every parent, and normalize nested `cached_tokens`. The v10 artifacts remain read-only evidence. 359 repository tests pass; the next workspace must freeze the remaining extension ceilings of 793 attempts, `$18.93009424`, and 956 real provider requests. The earlier v6 paragraph and detailed module row below remain historical handoff context.

Current v6 verification (2026-08-23, v27 remediation): v26 live-validated schema-only proposal, stable correction caching, exact guard-state preservation, and finalized fitness exclusion; candidate evaluation now fail-fasts after the first unfinalized trajectory. V27 then proved that omitting invocation-level data authorization could incorrectly turn `external_not_authorized` into Random-cohort substitution. Enabled data contracts now pause before cycle/snapshot/resolution unless the same invocation explicitly supplies `--data-external`. Slow H1/H2/H3/Update remain not live-verified. [`self-evolution-live-validation-audit-2026-08-23.md`](self-evolution-live-validation-audit-2026-08-23.md) contains the exact v25-v27 evidence.

Earlier v6 verification (2026-08-23): the standing-authorized v4-v9 remediation chain terminated exactly at its cumulative 800-attempt ceiling after `$1.03074748` settled cost, `$0.03244136` conservatively retained interrupted reservations, and 42 real provider fetches. V7 committed one complete 24-case Plan at Combined Binary F1 `0.666667` and authoritative pointers `round=1/cycle=0`; no workspace reached Slow cycle 1, and v9 correctly stopped at its frozen remaining cap of 129 attempts without resetting the campaign budget. Exact live-context inspection found provider-associated other-company news propagating through Basic Info, post-hoc, critic, and Round reflection; first-per-assessment meta sampling hiding richer root causes; a single-Plan Round reflector fabricating horizontal value by copying the critic; uninterpretable document hashes repeated in routing context; and a redundant terminal LLM rewrite that usually changed nothing but sometimes erased hypotheses or falsely resolved questions without new evidence. At that checkpoint, runtime removed the terminal LLM call and used a deterministic closure; v25 later proved that changing `decision` during that closure was itself semantically invalid and superseded it with exact guard-stop preservation.

| Area | Spec | Code | Status | Notes |
| --- | --- | --- | --- | --- |
| Meta mechanism | [`AGENTS.md`](../AGENTS.md), [`spec/README.md`](../spec/README.md) | [`scripts/lint_repo.sh`](../scripts/lint_repo.sh), [`.githooks/pre-push`](../.githooks/pre-push) | Done | Spec-first work, progress/memory hygiene, repository lint, and Git checkpoint rules are active. |
| Vision | [`spec/vision.md`](../spec/vision.md) | None | Spec Done | Defines a thesis-centered stock research system, not an order or portfolio engine; historical learning now has coupled Plan and Signal evolution time scales. |
| Architecture | [`spec/architecture.md`](../spec/architecture.md) | None | Spec Done | Defines the operating spine, module boundaries, point-in-time discipline, fixed Anchor plus three issuer-owned dataset roles, Fast Plan / Slow Signal loop, and immutable cross-workspace historical Plan warm starts. |
| Spec module map | [`spec/src/stock_opportunity_agent/README.md`](../spec/src/stock_opportunity_agent/README.md) | None | Spec Done | Active spec tree includes Raw Info, reusable LLM Agent harness, Signal Library, and the replacement evolution runtime. |
| Models | [`spec/src/stock_opportunity_agent/models.md`](../spec/src/stock_opportunity_agent/models.md) | [`src/stock_opportunity_agent/models.py`](../src/stock_opportunity_agent/models.py), [`tests/test_models.py`](../tests/test_models.py) | Started | Core serializable thesis, score, decision, evidence, review, experiment, and version records are implemented. |
| Config | [`spec/src/stock_opportunity_agent/config.md`](../spec/src/stock_opportunity_agent/config.md) | [`src/stock_opportunity_agent/config.py`](../src/stock_opportunity_agent/config.py), [`tests/test_config.py`](../tests/test_config.py) | Started | Validated defaults, JSON loading, environment overrides, and secret-safe public serialization are implemented. |
| Data | [`spec/src/stock_opportunity_agent/data.md`](../spec/src/stock_opportunity_agent/data.md), [`spec/src/stock_opportunity_agent/data/raw_info.md`](../spec/src/stock_opportunity_agent/data/raw_info.md), [`spec/src/stock_opportunity_agent/data/resolution.md`](../spec/src/stock_opportunity_agent/data/resolution.md), [`spec/src/stock_opportunity_agent/data/backfill.md`](../spec/src/stock_opportunity_agent/data/backfill.md), [`spec/src/stock_opportunity_agent/data/historical_news.md`](../spec/src/stock_opportunity_agent/data/historical_news.md) | [`src/stock_opportunity_agent/data/`](../src/stock_opportunity_agent/data/), [`scripts/backfill_historical_data.py`](../scripts/backfill_historical_data.py), [`tests/test_data.py`](../tests/test_data.py), [`tests/test_data_resolution.py`](../tests/test_data_resolution.py), [`tests/test_data_backfill.py`](../tests/test_data_backfill.py), [`tests/test_historical_news.py`](../tests/test_historical_news.py), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py), [`tests/test_evolution_control.py`](../tests/test_evolution_control.py) | Started | Raw Info is an explicitly identified global append-only oracle outside evolution workspaces. One local-first `EvidenceResolver` serves Basic Info and Signals with deterministic exact spans, complete document/hash lineage, durable acquisition limits, independently authorized adapters, structured DataGaps, and a derived capability backlog. Company-scoped news now requires a strong issuer name or boundary-matched ticker in visible title/body text; provider association metadata alone is filtered with durable events while complete Raw Info remains unchanged. Structured market context is selected on complete non-overlapping JSON-row offsets before model metadata normalization. New broad-research contracts use wildcard provider/capability/source-type authorization for every historical adapter registered by the frozen code revision, so future Signal types are not blocked by today's allowlist; absent adapters and genuine provider/history gaps remain fail-closed. Semantic source aliases route stable Signals to SEC facts, core-form filing bodies, Alpha Vantage news and point-in-time transcripts, and historical prices. Compatible acquisition failures are reused, provider fallback remains catalog ordered, and transcript availability is anchored to the provider-reported earnings date rather than the current retrieval time. Price documents retain adjusted-close series for deterministic market Signals. The local oracle contains 3,757 documents; all 24 exact round-1 cases have point-in-time company news, while one provider response remains explicitly saturated at 1,000 rows. Current-only profile endpoints still fail closed. |
| LLM capability | [`spec/src/stock_opportunity_agent/llm.md`](../spec/src/stock_opportunity_agent/llm.md) | [`src/stock_opportunity_agent/llm/`](../src/stock_opportunity_agent/llm/), [`tests/test_llm_model_registry.py`](../tests/test_llm_model_registry.py), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py) | Started | Provider catalog and generic harness remain reusable, but neither active Signal evolution track is a free-form tool loop. Signal Mining uses four narrow structured roles (`H1/H3` and `E1/E2`) plus a deterministic local H2 shortlist. Signal Update has one narrow `no_change/defer/update` role after local target and issuer-disjoint induction/holdout selection; no actionable target or insufficient local evidence makes zero Update-model calls. Structured production roles persist exact valid responses and failure-only malformed text, usage, and hashes. V59 live-verified one-call H1, zero-call H2, and the two-stage strong-query boundary: full-document near-matches advanced, but insufficient exact excerpts still prevented H3. Bootstrap is single-cycle, so Update and E1/E2 now require an ordinary Fast-derived run. |
| Memory | [`spec/src/stock_opportunity_agent/memory.md`](../spec/src/stock_opportunity_agent/memory.md) | [`src/stock_opportunity_agent/memory/`](../src/stock_opportunity_agent/memory/) | Started | File-backed signal/theme/playbook memory exists; broader company/thesis/review memory remains incremental. |
| Themes | [`spec/src/stock_opportunity_agent/themes.md`](../spec/src/stock_opportunity_agent/themes.md) | [`src/stock_opportunity_agent/themes.py`](../src/stock_opportunity_agent/themes.py) | Started | Cold-start industry-chain theme maps are implemented; live theme discovery remains spec-only. |
| Cases | [`spec/src/stock_opportunity_agent/cases.md`](../spec/src/stock_opportunity_agent/cases.md), [`spec/src/stock_opportunity_agent/cases/packets.md`](../spec/src/stock_opportunity_agent/cases/packets.md) | [`src/stock_opportunity_agent/cases/`](../src/stock_opportunity_agent/cases/) | Started | Outcome definitions, inflection candidates, control matching, and packet construction are implemented. The approved v13 manifest uses five mature 2025 dates, keeps every issuer identity with at least one case passing the point-in-time normal-stock gate, and freezes a separate 16-case Anchor. It contains 3,511 issuers/14,575 cases: Anchor 16/16, Discovery 2,096/8,755, Evolution Validation 875/3,623, and Locked Test 524/2,181. Security identity is common-stock/active/CIK/exchange/listing-date/SPAC filtered; each case additionally requires at least $1m pre-date average dollar volume and a clean adjusted-price window. The user reviewed the exact identity-decision and Anchor hashes before approval; Locked Test remains sealed. |
| Packet signals | [`spec/src/stock_opportunity_agent/signals.md`](../spec/src/stock_opportunity_agent/signals.md) | [`src/stock_opportunity_agent/signals.py`](../src/stock_opportunity_agent/signals.py) | Started | Existing deterministic `ResearchPacket` measurements remain isolated from the new adaptive Signal Registry. |
| Signal Library | [`spec/src/stock_opportunity_agent/signal_library.md`](../spec/src/stock_opportunity_agent/signal_library.md) | [`src/stock_opportunity_agent/signal_library.py`](../src/stock_opportunity_agent/signal_library.py), [`configs/signals_v1.json`](../configs/signals_v1.json), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py), [`tests/test_signal_financials.py`](../tests/test_signal_financials.py) | Started | The enabled-only Registry exposes 14 source-backed seed Signals; `market_cap` and `pilot_to_volume` remain disabled. `SignalExecutor.prepare_inputs` drives both complete-Registry readiness and execution. Adaptive case retrieval omits executed refs before one compact-card selection call, normalizes local formatting, caps each batch at four Signals and two LLM Signals, and retains executor fingerprint no-op as a second guard. Complete Raw Info stays local for fingerprints and final evidence validation; at most two soft Signals share one deduplicated deterministic source projection of 32,000 characters, model citations map uniquely back to original Raw Info spans, and per-Signal parse/validation/unavailable fallback remains independent. `unavailable` rejects supporting or counter-evidence at the value-object/parser boundary. Mining induction issuers remain excluded from paired effectiveness; insufficient independent coverage stays durable `provisional`, and stable promotion thresholds/recovery remain unchanged. |
| Scanner | [`spec/src/stock_opportunity_agent/scanner.md`](../spec/src/stock_opportunity_agent/scanner.md) | None | Spec Done | Defines non-LLM universe filtering and current-state-aware candidate generation. |
| Research / LLM | [`spec/src/stock_opportunity_agent/research.md`](../spec/src/stock_opportunity_agent/research.md) | [`src/stock_opportunity_agent/research/`](../src/stock_opportunity_agent/research/), [`tests/test_cold_start.py`](../tests/test_cold_start.py) | Started | Formal cold start and Ralph source/acquisition diagnostics remain; the older broad information-plan experiment is explicitly not a second active evolution engine. |
| Information-plan and Signal evolution | [`spec/src/stock_opportunity_agent/research/scheme_evolution.md`](../spec/src/stock_opportunity_agent/research/scheme_evolution.md), [`spec/src/stock_opportunity_agent/research/evolution_runtime.md`](../spec/src/stock_opportunity_agent/research/evolution_runtime.md), [`spec/src/stock_opportunity_agent/research/evolution_dashboard.md`](../spec/src/stock_opportunity_agent/research/evolution_dashboard.md), [`progress/self-evolution-audit-2026-08-14.md`](self-evolution-audit-2026-08-14.md), [`progress/self-evolution-audit-2026-08-22.md`](self-evolution-audit-2026-08-22.md), [`progress/self-evolution-live-validation-audit-2026-08-23.md`](self-evolution-live-validation-audit-2026-08-23.md) | [`src/stock_opportunity_agent/research/scheme_evolution.py`](../src/stock_opportunity_agent/research/scheme_evolution.py), [`src/stock_opportunity_agent/research/evolution_runtime.py`](../src/stock_opportunity_agent/research/evolution_runtime.py), [`src/stock_opportunity_agent/research/evolution_dashboard.py`](../src/stock_opportunity_agent/research/evolution_dashboard.py), [`scripts/evolve_information_schemes.py`](../scripts/evolve_information_schemes.py), [`scripts/run_information_plan_evolution.sh`](../scripts/run_information_plan_evolution.sh), [`tests/test_data_resolution.py`](../tests/test_data_resolution.py), [`tests/test_scheme_core.py`](../tests/test_scheme_core.py), [`tests/test_evolution_control.py`](../tests/test_evolution_control.py) | v7 Ordinary MVP Verification | V112 completed and authoritatively committed one real 24-case Fast round at F1 `0.6364` (precision `0.875`, recall `0.5`) after 184 successful calls and `$0.24501176`, then stopped before Slow because new routing-closure fields were incorrectly passed into the strict learning-event schema. Routing decisions now expose a stable explicit learning projection, post-pointer replay is idempotent, and `slow_bootstrap` can hash-bind exactly one compatible committed Fast boundary so a repaired successor consumes its learning/meta/capability derivatives without mutating the source or fabricating a Fast pointer. Live Slow execution and next-Fast Registry visibility remain the active verification step. |
| Scoring | [`spec/src/stock_opportunity_agent/scoring.md`](../spec/src/stock_opportunity_agent/scoring.md) | None | Spec Done | Defines theme, segment, company, risk, and final opportunity scores. |
| Ranking | [`spec/src/stock_opportunity_agent/ranking.md`](../spec/src/stock_opportunity_agent/ranking.md) | None | Spec Done | Defines segment and cross-market watchlist ranking. |
| Monitoring | [`spec/src/stock_opportunity_agent/monitoring.md`](../spec/src/stock_opportunity_agent/monitoring.md) | None | Spec Done | Defines catalyst monitoring, validation-contract checks, and research-state transitions. |
| Review | [`spec/src/stock_opportunity_agent/review.md`](../spec/src/stock_opportunity_agent/review.md) | None | Spec Done | Defines outcome review, earnings validation, error labeling, and signal attribution. |
| Meta-learning | [`spec/src/stock_opportunity_agent/meta_learning.md`](../spec/src/stock_opportunity_agent/meta_learning.md) | FIFO Plan meta implemented in evolution runtime | Started | Round meta is grounded in new experiments and fixed at 10 entries by default. Durable entries preserve complete original, vertical, and horizontal layers; the model-facing view is deterministic, aggregate-complete, recency-weighted, capped at 48,000 characters, and selects the richest available original reflection per assessment rather than hiding later root causes behind an early blank sample. A horizontal role call now requires at least two new Plan records. Append and whole-entry FIFO eviction remain the only window mutations. Broader system-level version governance remains spec-only. |
| Reports | [`spec/src/stock_opportunity_agent/reports.md`](../spec/src/stock_opportunity_agent/reports.md) | None | Spec Done | Defines watchlists, cards, reviews, and audit bundles. |
| Orchestration | [`spec/src/stock_opportunity_agent/orchestration.md`](../spec/src/stock_opportunity_agent/orchestration.md) | [`src/stock_opportunity_agent/orchestration.py`](../src/stock_opportunity_agent/orchestration.py), [`scripts/run_cold_start_formal.py`](../scripts/run_cold_start_formal.py), [`scripts/evolve_information_schemes.py`](../scripts/evolve_information_schemes.py), [`scripts/run_information_plan_evolution.sh`](../scripts/run_information_plan_evolution.sh) | Started | Evolution CLI supports local preflight, label-free Raw Info migration, exact dataset approval, v6 freeze, bounded `run-cycle`, continuous `run-loop`, and pointer-driven Ctrl+C resume. The manual `approve-signals` path is removed; exact validated candidates auto-promote inside the recoverable cycle transition. `new --data-external` freezes the wildcard broad-research profile with `1000/10000` request ceilings and remains zero-network; resume repeats the data flag, while LLM execution retains its separate exact-hash acknowledgement. Locked Test and unvalidated Signal mutation remain fail-closed. |

Current Signal remediation handoff: [`signal-remediation-verification-2026-08-21.md`](signal-remediation-verification-2026-08-21.md) records the three-layer Raw Info, then-active Agent-contract, and paired-promotion repair. A real isolated AMD historical run and a later wildcard-resolver replay both resolved all 14 stable Signal inputs and produced 13 evidence-backed values or semantic judgments; the only unavailable result was a legitimate absence-of-action finding. Those historical live Mining/Update invocations predate the current locally orchestrated Update pipeline. Existing frozen workspaces are not widened; a fresh contract gets unrestricted registered-adapter Raw Info authorization from the single `new --data-external` flag.

Latest Signal Mining redesign: the active Mining path is a local dual-track controller rather than the earlier Generic-Agent tool loop. Hypothesis cycles perform one H1 portfolio call, one label/identity-hidden H2 ranking call for all hypotheses, local positive/control feasibility with independent case reservation, then one H3 evidence contrast for at most two hypotheses. Every third cycle runs label-hidden E1 extraction followed by label-revealed E2 discovery. Company briefs use bounded point-in-time profile fields and Raw Info coverage, models can rank only opaque allowed case refs, and induction/effectiveness issuers cannot overlap. Outcomes distinguish promoted, provisional, rejected, and refined work without weakening stable promotion. The final scoped DeepSeek verification completed H1/H2/H3 in three calls for `$0.003969`; two unsupported comparisons became durable refined hypotheses, no candidate was fabricated, H2 contained neither identity nor outcome, H3 disclosed labels only after local selection, and Locked Test remained sealed. The local probe inventory contained only two eligible issuers and unavailable profile descriptions, so it validates control flow and privacy but not broad-universe mining yield.

Latest Signal Update redesign: every Fast selection persists a bounded reason/applicability decision, and every committed result becomes an append-only event under its exact Signal version. Full events retain Plan/case lineage locally; the selector sees only a compact identity-free profile with the complete state/outcome matrix, distinct-observation attribution, and recurring multi-issuer context tags. Effectiveness deduplicates the same case/ref/input across Plans while their distinct selection reasons remain auditable. A Fast group's learned profiles freeze at its starting committed-round cutoff, including after restart. Slow Update locally ranks up to three repeated exact-version issues, suppresses unchanged retries per target, executes each `vCurrent` over the same deterministic issuer-distinct Discovery sample, reserves a separate hidden holdout before each invocation, and makes at most one bounded semantic `no_change/defer/update` role call per locally prepared target. Per-target failures and recovery fingerprints are isolated inside one portfolio audit; no actionable target still means zero Update calls. `vNext` preserves static identity/semantics and remains isolated until existing contract, fixture, and paired holdout gates pass. The former active Update Generic-Agent tools and workflow adapter are removed.

Post-live Signal Mining persistence hardening: feasible H1 reserve hypotheses beyond the two-hypothesis H3 contrast budget are recorded as explicitly deferred refined work, so they remain visible to the next cycle instead of existing only in the audit trail.

Latest Signal routing remediation: the paid `deepseek-v4-flash-production-20260822-015342` audit showed that two-stage category/card routing consumed 329 of 800 external attempts and 395 already executed refs were selected before the executor skipped them. Production retrieval now exposes only unexecuted compact cards in one call, treats an exact empty array as valid no-match, fails closed with cumulative usage when malformed output remains invalid after correction, and appends no empty Signal batch. Point-in-time resolution, deterministic execution, soft-Signal evidence validation/correction, exact response caching, Mining/Update workflow validation, paired candidate testing, atomic promotion, and next-cycle Registry visibility remain covered.

Latest proposal remediation: `deepseek-v4-flash-signal-context-window-20260822-v3` proved that the provider could return a schema-valid but exact historical-parent copy for all three outer proposal attempts because the engine-level duplicate rejection was not fed back into the proposer. Exact-parent equality is now validated inside the proposer's one-correction loop, every request explicitly forbids parent copying, and proposal attempts carry deterministic change focuses for `B/H_init`, `H_reflect`, then `H_analyse`. The v3 workspace remains immutable fault evidence at round/cycle `0/0`.

Latest end-to-end Signal verification: contract-bound workspace `deepseek-v4-flash-signal-context-window-20260822-v4` committed Fast round 1 and Slow cycle 1 over 24 cases with Combined Binary F1 `0.583333` (`TP=7/FP=3/TN=7/FN=7`), 301 completed external attempts, `$0.525076` actual cost, and Locked Test sealed. All 48 readiness checks were `14/14`; the runtime made 289 resolved Signal-input resolutions, executed 159 changed fingerprints, and skipped 130 unchanged fingerprints. Of 159 persisted results, 94 were non-unavailable and every one retained only literal, point-in-time, fingerprint-bound evidence. The audit also found one pre-fix `customer_concentration` result that was `unavailable` yet carried eight irrelevant citations, six nonliteral; the value validator's unavailable early return had bypassed evidence checks. The current code rejects that exact artifact, supplies indexed correction feedback, and passes its exact failure replay, but v4 remains immutable pre-fix evidence and a fresh contract is required for post-fix external revalidation. Its committed meta entry contains all 24 original case reflections, one vertical Plan reflection, the horizontal error/Signal/search synthesis, and is included byte-for-byte in both Slow-agent initial workspaces. Historical seed F1 `0.727273` is retained only as context because its snapshot differs; `same_evaluation_snapshot=false` and `metric_delta=null` correctly prevent a causal regression claim.

Verification baseline: 331 repository tests pass with the bundled Python 3.12 runtime; repository lint is rerun at every change checkpoint. Coverage includes selector failure/no-match separation, Predictor prompt/schema agreement, canonical provider wire-body persistence/transport, both Signal Mining tracks, literal H1/H2/H3/E1/E2 role contracts, label/identity-hidden case ranking, local positive/control overlay, frozen signatures before label reveal, induction/effectiveness issuer separation, durable provisional classification, reasoned single-call eligible-card Signal routing, valid empty no-match without correction, pre-selection exclusion of executed refs, version-bound append-only learning, cross-Plan observation deduplication, identity-free learned cards, cycle-start learning cutoffs, zero-call Update skipping, Top-3 Update ranking/call bounds, per-target failure isolation, v1/v2 Update-audit recovery, one-call-per-target induction, local holdout isolation/promotion, integrated Raw Info -> soft Signal -> literal evidence -> reflection, unavailable/evidence coherence with indexed Signal correction feedback, exact-parent proposal correction with attempt-specific change focus, bounded exact-window LLM Signal context with full-document evidence validation, wildcard registered-adapter authorization and one-flag broad-profile freezing, complete-Registry readiness, semantic source aliases, compatible acquisition-failure reuse, core SEC filing fallback, fiscal-quarter transcript mapping and point-in-time filtering, paired Signal effectiveness promotion, unique case-only literal-span canonicalization, ordered provider fallback, readiness-based Random replacement before snapshot finalization, immutable Anchor failure, shared-data non-rejection both before and after candidate evaluation, retryable shared-data exit 75, four-way Predictor parsing and deterministic binary mapping, durable judgment/binary consistency, all eight label-revealed feedback cases, feedback-artifact validation, additive original/vertical/horizontal reflection persistence and legacy restoration, whole-entry FIFO eviction, outcome-aware but identity/context-free proposer handoff, explicit case-reflection and compact Plan-critic consumption, compact trajectory-free round reflection, anonymous parent-to-child structural comparisons, exact-snapshot-only metric deltas, ten-hour bounded process-level recovery after repeated temporary exit-75 failures, immediate propagation of deterministic failures and `Ctrl+C`, rejection/correction of the superseded binary role shape, absence of any active binary token-score call, compact Plan-critic trajectories that omit Raw Info/context/identity fields, unchanged Binary F1 selection, canonical Signal and CIK acquisition routing, paid malformed-JSON audit/cost/correction, proposal-level compact market-backbone correction, price metadata, catalog-ordered price providers, invocation-disabled frozen data policies, the normal-stock and per-case price/liquidity gates, fixed Anchor persistence, exact `16+8` sampling, union-confusion Combined F1, rare-class Validation diversity, restart conflict rejection, fitness gates, checkpoint cross-link recovery, staged Slow-validation and partial-Registry-transition recovery, cross-cycle promoted-Signal visibility, no historical Plan reevaluation, cumulative F1 parent selection, committed-only historical seed discovery, source-family and semantic diversity, immutable seed-manifest recovery and tamper rejection, first-run empty-pool fallback, current Top-K precedence over warm starts, current-target identity expansion, legitimate third-party evidence retention, global oracle identity, explicit data authorization, point-in-time evidence, existing expansion/backfill paths, and zero-network v5 launcher boundaries.

Current evolution handoff: `deepseek-v4-flash-information-resolution-v1` and all earlier execution workspaces are retained as immutable history. Their v1-v4 contracts cannot execute under the v5 runtime, and no cache, trajectory, metric, archive record, or completion pointer is migrated into a new workspace. V2-v10 record the resolved anonymity, CIK routing, malformed JSON, and Predictor-boundary faults described in the changelog. V11 was the first run to commit a healthy nonzero Fast round: its best round-1 Plan reached Combined Binary F1 `0.695652`; round 2 then rejected all candidates because Alpha Vantage's 25/day news quota left 6-7 rotating cases without any source evidence, even though two complete candidates had nonzero diagnostic F1 (`0.133333` and `0.25`). V11 must not resume after the market-backbone correction, but its exact committed best Plan is eligible as content-addressed parent context in a new contract-bound Seed Pool; its old F1 remains provenance only and is never imported into the new Top-K. The old 53-case approved manifest has no Anchor and remains infeasible. Approved v13's Evolution Validation pool contains 3,623 cases across 875 issuers with `3,387/171/62/3` case counts for `non_surge/2_3x/3_10x/10x_plus`; the 10x+ cases span AXTI and HYMC, so exact round sampling rotates across two issuer identities. The fixed Anchor contains seven matched controls plus CIEN, FTAI, ATI, NEM, MP, SNDK, MU, PRAX, and ONDS. The exact round-1 snapshot is `63d1c0769e976aec421b6d393c4b67c9d7b26f7552bce069bb6d9d6a07dfaef8`, and every one of its 24 cases now has point-in-time news in the global oracle. The historical `v13-next-token-v5` run completed all 48 binary-threshold candidate-case trajectories but produced `TN=10/FN=14/TP=0/FP=0`; it remains uncommitted at round/cycle 0 and therefore cannot seed any new run. Its Plan-critic overflow remains useful fault evidence: compact critic input keeps the diagnostic outcome/reflection/Signal information while excluding repeated Raw Info.

Latest paid verification: `deepseek-v4-flash-fourway-20260816-230058` recovered the observed SSL EOF under its exact cached contract and completed the first 24-case candidate with `TP=5/FP=1/TN=9/FN=9`, Combined Binary F1 `0.500`, precision `0.833`, and recall `0.357`. All 24 trajectories persisted the original four-way judgment and deterministic feedback; the user then requested a safe interrupt during candidate 2, leaving round/cycle pointers at zero. That revision remains fault/metric evidence but cannot use the new built-in supervisor after the next code commit.

Current gate: the user resolved the Predictor design tension by restoring the four-way opportunity boundary, and the exact v13 proposal, identity decisions, and Anchor remain human-approved. Because run contracts bind the exact code revision, built-in ten-hour recovery must start in a fresh workspace; that workspace now automatically freezes the best compatible committed historical parent seeds and validly falls back to the manual Plan when none exist. Earlier workspaces remain immutable evidence. Before enabling SEC acquisition, the operator must set `SOA_SEC_USER_AGENT` to a real application/contact identity; it cannot be inferred or fabricated. Massive/Stooq point-in-time market data remain authorized without SEC. Locked Test remains sealed.

Latest parent-reflection verification: `deepseek-v4-flash-parent-reflection-verification-20260817-v1` completed and committed one full Fast/Slow cycle after automatically recovering four DeepSeek SSL EOFs. Its 24-case child reached `TP=4/FP=1/TN=9/FN=10`, Combined Binary F1 `0.421053`, precision `0.800`, and recall `0.285714`. On the exact shared snapshot, reflection received the v11 parent F1 `0.695652`, child-minus-parent F1 `-0.274600`, `TP -4/FN +4`, removal of annual-filing and SEC-facts requests, and addition of the market backbone. Plan critic explicitly identified missing fundamental data as a false-negative pattern; compact round reflection completed with 5,152 input tokens and no trajectories or case ids. Round 1 and cycle 1 are committed, no Signal passed Slow validation, and Locked Test remains sealed.
