# Live Evolution Context Audit

visit_times: 11

## Trigger

Use this when auditing a real Information Plan / Signal evolution run, especially
when the request asks whether actual prompts and contexts match the design or where
tokens are being spent.

## Lesson

Code inspection is insufficient. Open the exact persisted request and response for
every reached role, parse the user payload, inspect literal source spans, and join
request hashes to attempts, per-case trajectories, rejection artifacts, committed
pointers, and the Registry hash. A failed real run is evidence that the current
contract does not run through; do not replace it with a historical success claim.

Audit value-level boundaries, not only field-name allowlists. Identity can re-enter
compact retrospective context through free-text information needs and then be copied
into Plan critic output, Round meta, and the next proposer even when case ids and Raw
Info fields are absent. Scan actual request values with the exact case alias inventory
before every retrospective/model handoff and before meta persistence.

Token accounting should start from provider-reported input tokens grouped by stage,
then measure repeated payload components directly. In this runtime, high-value checks
include zero learned profiles repeated per Signal card, HTML boilerplate in SEC literal
projections, the same Raw Info sent to several soft Signals, full original context sent
again for post-hoc reflection, repeated case packets across H3 hypotheses, and additive
meta entries sent in full. Keep complete artifacts locally even when the model-facing
view is normalized or compacted.

Finally, verify that selection contexts contain enough information to perform the
promised semantic job. A label-hidden Signal Mining ranker cannot rank hypothesis
applicability when every company brief lacks business, industry, sector, and size
fields, even if its JSON shape and anonymity checks pass.

## Resolution (2026-08-23)

The v6 remediation keeps complete Raw Info, trajectories, and additive three-layer
meta durable while sending only bounded deterministic projections. It also treats
request-byte plus output-ceiling reservation as pre-network control flow, validates
tagged evidence transitions and projection-to-raw literal spans, batches at most two
soft Signals, scans both incoming and accepted retrospective values for identity and
fixed-semantics drift, and requires semantically usable H2 profiles before H2/H3.
Old v1-v5 workspaces remain immutable audit evidence; only a newly frozen v6 contract
may advance pointers after its exact hash is authorized.

## Live validation addendum (2026-08-23)

Structured literal refs need actionable correction errors, not only strict local
validation. A real controller can cite a correct contiguous SEC literal under an
adjacent projection chunk id, use ellipses between two market rows, or concatenate
non-contiguous facts. Canonicalize only when the literal has exactly one occurrence
across all visible projections. Otherwise identify the precise evidence index and
matching projection ids, explicitly forbid non-contiguous/reordered/paraphrased text,
allow one correction, and then fail closed without advancing the round pointer.

Evidence-transition equality must compare provenance, not explanatory wording. A
real finalize response may restate `claim` while preserving the exact Basic or
Signal source tuple; rejecting that as new evidence is stricter than the design.
Likewise, if a role is required to return a versioned `signal_ref`, the current batch
must expose that exact field. Local code may remove redundant legacy citation keys or
expand an unversioned id only when every canonical field is present and one current
batch result matches; it must never guess across versions or batches.

Bounded correction is only meaningful when feedback is executable. For Signal
citations, expose the exact valid supporting/counter indices per versioned ref and
name the invalid output item/ref/group/index. For retained Basic citations, use the
already-supplied prior evidence array as the canonical indexed inventory and report
missing/unexpected fields; do not duplicate that array in another prompt block or
reconstruct a missing literal locally. Strict-but-generic feedback can make a model
repeat the same error and reject otherwise viable candidates without strengthening
the evidence boundary.

Token reserves and context ceilings must use compatible units. If request preflight
conservatively counts each canonical wire byte as one token, a 36k terminal reserve
cannot cover a Predictor packet that repeats a 32k-character Basic projection plus
all Signal rounds and JSON escaping. Keep the conservative preflight; derive a
separate Predictor projection that sends source/DataGap coverage, the final state,
compact Signal conclusions, and only cited Signal evidence. Measure the anonymized
canonical payload in UTF-8 bytes and freeze that ceiling in the run contract while
retaining complete Basic Info and trajectories locally.

Privacy checks are also part of live control-flow performance. A full-market alias
inventory can contain tens of thousands of expanded names; recompiling every alias
for every nested string may leave one CPU saturated for minutes before a request is
even reserved, which looks like a provider stall while consuming no ledger entries.
Preserve the complete recursive mask and independent scan, but compile the exact
case-sensitive prose and case-insensitive URL matchers once per payload traversal and
reuse them across leaves. Audit the last completed attempt plus provider ledger before
diagnosing such a silent interval, and benchmark with the real inventory scale.

Inspect the entire concatenated system prompt, not just its leading role-specific
instruction. A batch role can correctly request a `results` wrapper and then append a
generic single-result “return exactly” example that weakens or contradicts it. Versioned
outer refs and unversioned inner domain ids must be shown together in one batch example;
when identity validation fails, correction needs the returned and expected values for
outer ref, inner id, and integer version. A generic “identity mismatch” lets a model
repeat the same syntactically valid but semantically wrong id and doubles paid attempts.

## Content-fidelity addendum (2026-08-23)

An anonymity-clean context can still be semantically contaminated. Provider ticker
association or company-id routing is not enough for company news: inspect visible
title/body text for a strong issuer name or boundary-matched ticker before Basic Info,
Signal, or H3 use. In one committed 24-case round, 23 of 107 news projections lacked
the target issuer and one false-negative reflection converted four other companies'
news into a learned “ignored commercialization” root cause that the critic and Round
reflector repeated.

Durable additive meta does not guarantee faithful model-facing meta. A compact view
that takes the first case per assessment can select blank or validation-fallback
reflections while hiding later concrete analyst diagnoses. Preserve every durable
case, but choose bounded representatives by diagnostic content and keep an opaque
case index for audit. Horizontal reflection also requires at least two new Plans;
with one Plan it can only paraphrase the vertical critic, so use a deterministic
zero-call horizontal layer.

Finally, keep cryptographic fingerprints local unless a model can perform a semantic
operation on them. The selector already receives only unexecuted cards, and the
executor owns fingerprint no-op; replaying hundreds of opaque hashes in routing
requests adds tokens without information.

## Terminal-fidelity addendum (2026-08-23)

A role should not exist merely because a phase name suggests one. When a local guard
ends research after the last initialize/reflect response and no new evidence is
available, an LLM finalize rewrite has no additional input from which to improve the
state. Compare the actual field-level deltas: if most calls are no-ops and the few
changes erase hypotheses or reclassify unanswered questions, close deterministically
while preserving every analysis/provenance field. This saves attempts and, more
importantly, prevents late ungrounded rewriting of a correct root cause.

Provider prefix caching also needs evidence rather than assumptions. Place the largest
semantically stable user-data object before case-dynamic values in canonical payloads,
without promoting untrusted content into the system role. Persist provider-reported
cache hit/miss token counts, but keep pre-send token and cost gates conservatively priced
as cache misses. Measure common prefixes by replaying real payload values, then verify
actual hit rates only on the next live run.

## Boundary-language addendum (2026-08-23)

Guard scanners must distinguish an affirmative semantic change from prose that repeats
the prohibition itself. A model saying “without calculating probabilities” is honoring
the fixed boundary; substring detection that sees only “probabilities” wastes correction
attempts and can reject the better Plan. Return the exact affirmative matched phrase so
the one allowed correction is actionable.

Likewise, a prompt-side exploration focus is not enforced merely because the whole Plan
hash changed. Validate the named field group against every supplied parent after parsing:
a `B/H_init` attempt that changes only `H_analyse` destroys attribution even though it is
not an exact clone. Provider usage schemas also vary across compatible endpoints; accept
both direct cache-hit fields and a validated nested cached-input count, while continuing
to budget every input token as a miss.

## Projection-order addendum (2026-08-23)

Stripping HTML after raw fixed-width chunking is insufficient. A chunk can start inside
`style=` or end inside an XBRL tag, and raw-token query ranking can prefer attributes
over readable facts. For filing markup, normalize the complete document for ranking and
window boundaries first, then map each readable window back to exact raw offsets. Keep
the raw span literal and derive the model view with complete-tag removal and entity
decoding. Verify the exact failed request, not just a balanced synthetic HTML fixture.

Literal existence is also weaker than claim support. A model can cite a beginning cash
balance while claiming a beginning-to-ending decline. A local quantitative entailment
gate can remain deterministic by grouping Basic refs with the same claim and requiring
every normalized numeric quantity in the claim to occur in the union of their exact
literals. This permits a legitimate two-endpoint market claim while rejecting an
unsupported composite fact without pretending to solve general semantic entailment.

## Cross-layer preservation addendum (2026-08-23)

A structured Signal ref proves provenance identity, not that a downstream claim is
entailed by the referenced literal. Validate quantitative claims against the exact
Signal evidence when the ref is introduced; after that batch leaves the visible
context, keep the retained Signal claim immutable. Also reject citations touching an
internal fixed-window edge, because overlap may contain the complete clause while an
edge fragment such as `$1,` invites a plausible but false completion.

Audit compact views against the structure actually handed between layers. A post-hoc
compactor written for the raw Basic bundle silently emitted an empty source index when
its real input was already the Predictor projection. Correct predictions need positive
learning too: require a concrete decision driver rather than accepting an all-empty
failure-shaped reflection. Finally, identity tests must cover target brands embedded in
product/property names; four-letter brands can be distinctive even when short tickers
remain case-sensitive.

When overlapping projections expose one complete clause and one truncated copy, a model
may quote the complete clause but attach the neighboring projection id. Treat the id as
locally repairable provenance only when the unchanged quote has exactly one occurrence
across the entire visible lineage; then map through that unique projection and still
apply edge checks. A correction call is wasteful and can destroy valid evidence when
the quote itself is already uniquely verifiable.

Quantitative literal gates need exact unit equivalence, not only digit equality. Model
prose may express a raw SEC integer as an exact billion value; treat the unscaled token
and exact Decimal-scaled value as alternatives for an explicit unit, with no tolerance
or rounding. Keep the unscaled alternative because a table literal may carry the number
while its unit header is outside the quoted span.

Fixed-semantics scanners must also distinguish replacing a threshold from describing the
frozen one. A correct post-hoc explanation that evidence stayed below the doubling
threshold is learning, not semantic drift. Match affirmative set/use/change actions or
numeric replacements rather than the bare noun.

## Forced-stop fidelity addendum (2026-08-23)

A runtime guard is control-plane evidence, not a research conclusion. In an actual
v25 case, the last H_reflect response returned `decision=continue` with two open
questions and three pending information needs, and the next routing response selected
four unexecuted Signals. A conservative token preflight then stopped the batch, after
which the old deterministic closure changed the state to `decision=finalize`, cleared
the needs, and persisted `stop_reason=finalized` plus
`termination_trigger=budget_exhausted`. That makes an incomplete trajectory look
fitness-valid and changes the Predictor context without evidence. Preserve the exact
last model-authored state, record the guard as the stop reason, allow a bounded
diagnostic prediction, and let the existing finalized fitness gate exclude it.

Provider-facing examples are also behavioral priors even when the prompt says not to
copy them. The v25 proposer returned all three executable H_* example strings exactly,
causing a preventable correction. Describe exact keys, types, and semantic requirements
without embedding a complete candidate. Keep legacy-echo validation, and give initial
and correction attempts one byte-identical system prompt plus a stable
`proposal_context` prefix followed by null-or-object validation feedback.

The same rule applies to H1. In v36 the first hypothesis copied the complete order
example and the remaining portfolio stayed in that example's domain while ignoring
the supplied earnings/production/estimate/revenue needs. Use a schema-only H1 contract;
when bootstrap needs exist, require every hypothesis to share at least two normalized
non-generic topic terms with one need. This validates grounding without having local
code invent or select a hypothesis, and still permits an explicit empty portfolio.

## Citation-usability addendum (2026-08-23)

An evidence contract can be correct while its model view still makes compliance
needlessly unlikely. In actual initialization prompts, dense market JSON encouraged the
model to construct a shorter object containing only `adjusted_close` and `as_of_date`;
that was semantically faithful but not a contiguous literal. Keep the strict literal
gate and tell the role to copy a complete visible row. If correction returns the same
rejected provenance, make the required transition explicit—replace that item with a
valid visible reference or remove it—rather than silently repairing or dropping it.

Also separate evaluation semantics from issuer facts in the reasoning prompt. The fixed
six-month doubling outcome is a label definition, not a company target whose "terms"
need research. Without that sentence, a superficially sensible H_init can spend its one
information need asking an unanswerable meta-question instead of seeking catalysts,
financial capacity, market confirmation, or counter-evidence that bears on repricing.

## Empty-routing addendum (2026-08-23)

Schema-valid empty routing can still contradict the exact context. One paid request
asked for operating cash flow while its visible cards included
`operating_cash_flow_margin:v1`; accepting `selections=[]` discarded a directly relevant
Signal and made deterministic finalization look like evidence exhaustion. Use a narrow
contradiction gate before accepting empty: only an exact phrase of three or more
consecutive normalized Signal-ref words in a need triggers one semantic correction.
Do not expand this into fuzzy retrieval or locally choose the ref; an unmatched empty
must remain a legitimate no-match result.

## Auxiliary-tag addendum (2026-08-23)

Do not let auxiliary routing metadata destroy a semantically useful selection. Signal
cards expose categories, so a model may naturally copy `catalysts`, `risks`, or
`product` into `context_tags` even when the narrower tag vocabulary uses different
terms. Tags were designed as locally normalized coarse hints: discard unknown strings,
deduplicate, and cap them. Preserve correction and rejection for wrong Signal refs,
missing fields, invalid reason/role enums, or malformed tag containers, which can
change execution semantics rather than merely losing an optional hint.

## Current-period addendum (2026-08-23)

Point-in-time legality does not imply decision-time relevance. An SEC Company Facts
document fetched and available in 2025 can still contain decades of old facts; if a
company migrated from `Revenues` to
`RevenueFromContractWithCustomerIncludingAssessedTax`, an incomplete concept alias
list can silently label 2018 as “latest.” Inspect actual fact end dates in Signal
evidence, support both assessed-tax revenue concepts, and require the current period
to be within a bounded reporting-age window. Old comparison periods may remain valid
only behind a fresh current period.

Derived deterministic metrics also need an honest downstream citation path. Raw fact
rows cannot literally contain a computed growth rate, so requiring every reflected
number to occur only in raw evidence makes the useful Signal output impossible to
state. Permit the exact validated `metric=value` interpretation through its Signal
ref, while rejecting rounded percentages, unit conversions, and extra source values.
This preserves both the computation and the raw evidence boundary.

## Question-state addendum (2026-08-23)

Adopting useful evidence does not prove that every active information need was
answered. Forcing all need text to change can manufacture resolution or blur an
unchanged question, while allowing every unchanged need can leave an answered topic
stale. Preserve an unanswered need byte-for-byte, reject qualifier-only paraphrases,
and separately reject a newly resolved same-topic question coexisting with the exact
old need. Keep unavailable-to-belief/resolution validation independent of this rule;
one guard must not accidentally provide the only protection for another semantic
boundary. When both a citation defect and question-state defect are already locally
decidable, surface both in the one bounded correction.

## Correction-prefix addendum (2026-08-23)

Before deleting correction context, compare the exact initial/correction wire prefix.
A large shared projection may already be deduplicated within a batch yet still miss
provider caching because dynamic correction text changes the earlier system message.
Keep one conditional system prompt byte-identical across both attempts, keep stable
batch identity fields before source data, and append dynamic validation feedback after
the unchanged projection. This preserves complete correction evidence and conservative
cache-miss budgeting while making the whole common prefix cache-eligible. Verify the
canonical key order: a dynamic field sorted before the projection defeats the intended
prefix even when the in-memory insertion order looks correct.

## Fitness-impossible fail-fast addendum (2026-08-23)

Preserving an incomplete state is necessary but not sufficient for token safety.
Join each completed trajectory to the fixed fitness predicate before starting the
next case. If one unfinalized trajectory makes the candidate permanently ineligible,
persist its diagnostic prediction and exact state, then stop the candidate with the
full expected case set and completed subset. Do not convert the condition into a
fabricated execution failure, and apply the same check immediately after restart
reuses the checkpoint. A configurable contract flag must not claim the finalized
gate can be disabled when the scorer and parent-selection path enforce it
unconditionally.

## Authorization-neutral sampling addendum (2026-08-23)

Dry-run safety is not enough when control-plane posture can change durable
research inputs. If a frozen contract enables acquisition but the invocation
does not reauthorize it, pause before cycle creation and evaluation sampling.
Otherwise local resolver misses become `external_not_authorized`, which a
label-free readiness sampler can mistakenly interpret as genuine no-data and
use to replace Random cases. Inspect both external-call ledgers and the exact
snapshot: zero network calls do not prove the preview was state-neutral.

## Coverage-only no-op and applicability addendum (2026-08-23)

Apply a semantic invariant before paying a reasoning role. When every result in an
actual Signal batch was canonical `unavailable`, H_reflect received no usable evidence
and returned the complete ResearchState byte-for-byte, consuming nearly three thousand
tokens. Persist the batch, coverage, fingerprints, and usage, but keep the state exact
and route among remaining cards without reflection. Do not extend this shortcut to a
mixed batch: one available deterministic result can still justify a real update even
when neighboring soft Signals are unavailable.

An applicability description in a card is insufficient if routing can explicitly
classify a case into the excluded context and select the Signal anyway. Let the Signal
version own a small exclusion list from the existing context-tag vocabulary. Correct a
selection only when the model's own tag directly conflicts with that visible list;
never infer tags from issuer content, fuzzily classify the case, or choose a replacement
Signal locally. This catches a mature-mine commercialization contradiction without
turning all auxiliary tags into hard routing policy.

The stable correction-prefix rule applies to compact control roles as well as large
soft-Signal projections. H_init and Signal routing both lost most cache reuse because
their correction changed the system prompt; routing also placed dynamic failure fields
before part of its stable context. Use one conditional system prompt and one trailing
null-or-object validation feedback field. Keep every Basic projection, skill, need,
card, profile, prior result, rejected output, and validator error; cache optimization is
request layout, not context deletion.

## Cross-field and mixed-budget addendum (2026-08-24)

Validating quantities only inside evidence claims does not ground the other structured
state fields. A corrected H_init can narrow an invalid evidence claim while retaining
an unsupported year, quarter, or forecast in `current_beliefs`; a number appearing in
an unrelated market claim must not launder it. Bind every quantitative belief or
contradiction to one byte-identical validated evidence claim, and let multi-span facts
share that exact claim across refs.

Applicability routing also needs accepted case context, not just the open question. A
selector that sees only “growth projects” can invent an early-commercialization stage
for a mature miner and spend a soft Signal call that the full source later rejects.
Expose a bounded label-free ResearchState view with beliefs and evidence claims, never
the full Basic projection or source literals.

Finally, an exact pre-send budget stop late in a mixed Signal batch must not erase
deterministic work already completed locally. Execute the deterministic subgroup first,
then the soft subgroup, merge successful results into selector order, and preserve the
partial deterministic round if the soft request cannot be reserved. The case remains
`budget_exhausted` and fitness-ineligible; any paid initial soft usage before a blocked
correction still counts. When a soft citation fails at an internal projection edge,
name the evidence index, touched edge, and overlapping projection ids so the sole
correction can choose a complete visible clause without local evidence synthesis.

## Persisted-scope addendum (2026-08-24)

Semantic constraints that depend on an earlier model decision must persist across
rounds. A selector can correctly tag one commercialization selection as
`mature_operations`, have that selection rejected, and then choose the same Signal as
`general` on the next round. Preserve the selector-authored accepted tag history in
later routing context and apply the version-owned exclusion to the union of prior and
current tags; never infer issuer stage locally.

A shared LLM projection also needs per-Signal citation scope. Batching two Signals over
one union of documents can let one result cite a document supplied only for its peer,
which is predictable from the prompt rather than merely a bad response. Expose each
versioned ref's exact eligible projection ids and enforce that subset during literal
mapping, unique relocation, and overlap repair while retaining one shared provider
call.

Finally, role and privacy validators must inspect ordinary prose semantics, not just
schemas and alias presence. An incorrect prediction with every diagnostic array empty
is not useful reflection; require at least one concrete failure attribution. Research
Controller instructions may finalize evidence collection but cannot redefine the
Predictor's fixed four-way ontology. Identity masking must not derive generic prose
aliases such as `High` from a multi-word company name, because replacing a normal
adjective silently corrupts Plan meaning even though the target identity disappears.

Ontology guards have the same affirmative-versus-negative boundary as probability
guards. A real proposer first wrote “keeping the four-way judgment intact” and then
corrected it to “without altering the Predictor class ontology”; both faithfully
preserved the fixed boundary, but a bare ontology scanner rejected both and discarded
the proposal attempt. Remove only tightly shaped preservation phrases before checking
for a replacement class list. Do not scrub arbitrary `without ...` clauses, which
could hide an affirmative instruction later in the same sentence.

## Slow-bootstrap addendum (2026-08-24)

An ordered Fast-then-Slow loop can deadlock during cold start even when each role is
locally correct. Repeated label-hidden Fast trajectories ended at `no_signal_match`,
but the capability backlog aggregated only provider DataGaps; the missing Signal need
therefore prevented Fast commit while Slow had no legal trigger or input from which to
mine it. Do not fabricate a finalized Fast state, advance its pointer, or relabel a
rejected Plan as learning history.

Use an explicit, contract-frozen zero-Fast bootstrap instead. Its only cross-workspace
input is an immutable aggregation of `continue + no_signal_match` information needs
from the exact next rejected round. Mask the source case identity, retain counts rather
than case ids, and bind source contract/rejection hashes plus the stable Registry.
Exclude predictions, labels, post-hoc reflection, literal evidence, hypotheses, metrics,
and Plan definitions. The exception changes only the Slow trigger: H1/H2/H3, Update,
candidate execution, paired effectiveness, atomic promotion, and Locked Test remain the
ordinary gates, and the rejected Fast round stays outside committed history.

## Aggregate-identity addendum (2026-08-24)

Do not reuse a case-local identity masker as an aggregate structured-role rewrite.
The complete Discovery inventory intentionally derives leading brands so a concrete
case's source text cannot leak its issuer, but across thousands of issuers those brands
include protocol vocabulary such as `Open`, `Match`, `Alpha`, and `News`. In one exact
H1 request, global substitution corrupted source-type enums, backlog status/stop values,
stable Signal categories/functions, and ordinary comparative prose before any network
call was sent.

Keep the full recursive derived-alias mask and independent scan at each case/source
producer. Once those producers have emitted anonymous briefs, evidence packets, Signal
views, or bootstrap needs, preserve the aggregate JSON exactly and scan it without
mutation for only strong identities: opaque ids, exact ticker-like aliases, and
multi-word formal-name components. Apply the same strong scan to Mining/Update output;
on a leak, reject into the bounded correction without echoing the leaking value. Never
silently rewrite an accepted schema, enum, identifier, candidate, or control value in
the name of output sanitization.
