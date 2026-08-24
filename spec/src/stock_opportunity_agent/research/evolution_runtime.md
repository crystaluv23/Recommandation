# Evolution Runtime Control Plane

## Status

Ready - v6 bounded-context, evidence-reference, and cumulative Signal-transition contract specified

## Purpose

Own the non-evolvable run boundary around the Information-Plan/Signal dual
loop. This module does not decide research strategy and is not part of the four
fields in an `InformationPlan`. It freezes inputs, discloses external requests,
enforces attempt/cost ceilings, caches exact responses, and inventories legacy
point-in-time artifacts before migration.

## Frozen Run Contract

One immutable, secret-free `EvolutionRunContract` binds:

- run id and schema version;
- dataset and reviewed split-manifest hashes;
- global Raw Info oracle id and initial inventory hash (diagnostic identity
  only; later oracle growth is not evolutionary state);
- initial stable Signal Registry version/hash;
- fixed `H_R/H_P/H_E/H_U` hash;
- role/model/provider/routing metadata;
- code revision and Python runtime;
- candidate/round/runtime limits, including a parent-selection seed used
  deterministically with each round id;
- the canonical historical Plan Seed Pool manifest hash produced by automatic
  committed-workspace discovery; an empty manifest is valid for the first run;
- a mandatory Fast-loop evaluation contract containing 16 fixed Anchor cases
  (`7/5/3/1`) plus 8 deterministic round-Random cases (`3/2/2/1`), primary and
  secondary metrics, the cross-cohort per-company cap, deterministic rotation
  seed, fitness eligibility, and bounded proposal/correction counts;
- role sampling settings: Plan proposer temperature `1.0`, judge temperature
  `0.0`;
- maximum external attempts and cumulative cost;
- an independent source-data authorization block containing enabled status,
  allowed providers/capabilities/source types, and per-cycle/run request
  ceilings; and
- `locked_test_accessed=false` for ordinary evolution.

An existing contract path may be reused only if canonical content is exact.
API-key availability is a boolean preflight fact and the key value is never
stored.

Only `evolution-run-contract-v7` may execute. Older frozen contracts, including
v6, remain
readable for status/audit commands but run commands return
`legacy_contract_read_only`; no missing evaluation field receives an implicit
default. Before the first cycle creates requests or execution artifacts,
runtime verifies the exact Git revision, Python runtime, dataset hash, initial
enabled-Signal snapshot, historical Seed Pool manifest, and oracle id. On later cycles it verifies the current
stable snapshot against the last committed cycle output, not against the
initial contract snapshot. Evaluation snapshots are immutable recovery inputs
under the run workspace. Their existence does not prove round completion or
advance `state.json:last_completed_round`.
For v7, both model roles, code/runtime identities, and every consumed limit are
mandatory and type/range validated when the contract is loaded. Execution uses
those exact fields and never substitutes Python-side defaults.
The contract additionally freezes the fixed Predictor-semantics hash, the
available Basic-Info source-type catalog hash, a four-Signal/two-LLM-Signal
per-round ceiling, a 36,000-token terminal-plus-Predictor reserve, all
model-facing character ceilings, and role output-token ceilings. The frozen
role ceilings are 2,000 tokens for controller, routing, Predictor, post-hoc,
H1, and H2; 4,000 for proposer, critic, and one LLM-Signal batch; and 8,000 for
H3 and Update.
V7 additionally freezes `cycle_mode`. `fast_then_slow` requires a positive
`plan_rounds_per_signal_cycle` and no bootstrap manifest. `slow_bootstrap` is
single-cycle and requires exactly zero Fast rounds plus the hash of
`slow_bootstrap/manifest.json`. That immutable manifest contains only
identity-masked, label-hidden `no_signal_match` needs aggregated from compatible
next-round rejection artifacts, and binds their source contract/rejection
hashes and the exact input Signal Registry. Runtime verifies the manifest before
creating a cycle and rejects an empty diagnostic seed. The mode changes only
the Slow trigger; H1/H2/H3, Update, validation, promotion, Locked Test, attempt,
cost, and source-data policies are unchanged.
Freeze additionally rejects an empty stable Signal Registry. The clean-worktree
check is scoped to runtime-bearing tracked paths (`src/`, `scripts/`, and
`configs/`) plus untracked files under those paths; unrelated progress or memory
notes do not make the executable HEAD unreproducible.

Seed discovery is local, deterministic, and performs no model or provider
calls. A first-ever evolution root produces a valid empty
`seed_pool/manifest.json`. If a manifest was durably staged before the contract,
freeze reuses and verifies it rather than rescanning newly completed history.
Once the contract exists, resume requires the exact manifest hash and never
mutates the pool. Source artifacts may later disappear without changing the
snapshot because each selected Plan definition and all source hashes needed for
audit are copied into the manifest; changing the local manifest itself fails
closed before any external request.

## External Request Boundary

Every request is canonicalized and written under `requests/<hash>.json` before
network I/O. Role-specific validation enforces:

- Predictor calls contain neither the current target's identity aliases nor
  outcome fields;
- prediction-time controller, retrieval, and Signal calls contain no outcomes;
- the Information Plan proposer may receive only committed, anonymous,
  label-revealed additive FIFO reflection entries; this role-specific exception
  never admits company/case ids, Raw Info, literal evidence, research contexts,
  or Locked Test content;
- post-hoc reflection is the only Predictor stage allowed to receive truth;
- judge registrations are no-web and retries stay at one; and
- the request cites the frozen run-contract hash.

The post-hoc reflection boundary rescans the original anonymous context for
identity aliases, then treats the already validated immutable prediction and
numeric revealed truth as typed records. It does not rescan prediction enum
values as free identity text, because legitimate values such as confidence
`low` can equal a ticker alias (`LOW`).

Free-text scanning preserves alias type. Company names are matched
case-insensitively, while short uppercase ticker aliases are matched
case-sensitively. The current case's internal id, identity fields, source aliases,
composite formal-name components, suffix-stripped natural company names, and
distinctive leading brand tokens are independently stripped and masked before a
defense-in-depth scan of the assembled context. This still catches an explicit
`AN`/`LOW` ticker leak but does not misclassify ordinary prose such as "an
artifact" or "low liquidity". A common leading company-name word such as `High`
is not by itself a distinctive derived brand alias: the complete name and ticker
remain masked, while ordinary Plan prose such as "high decision relevance" must
remain byte-for-byte intact.
Distinctive non-generic leading brands of four or more alphanumeric characters are
included, so a four-letter brand reused inside a target-branded property or product
name cannot survive merely because the ticker matcher is intentionally case-sensitive.
Three-character leading brands remain eligible only when uppercase.

Predictor anonymity is case-local. The runtime must not pass the full approved
dataset's alias inventory into a case request scanner: broad market inventories
contain ambiguous one-to-five-character tickers and names such as `UBS` that can
also be legitimate third-party evidence in another company's news. Such a global
scan rejects valid anonymous evidence without strengthening target anonymity.

An attempt is reserved in `attempts.json` before the call. Reservation fails if
the attempt count or cumulative conservative cost ceiling would be exceeded.
Completion/failure updates the same durable entry. Exact responses live under
`cache/responses/<request_hash>.json`; reuse requires the exact request hash and
does not consume another attempt.

Before cache lookup can fall through to attempt reservation or network I/O,
runtime computes canonical UTF-8 bytes for the exact provider request and adds
the frozen output-token ceiling as a conservative case-token reservation. A
request whose reservation exceeds the remaining case budget is never sent.
Adaptive research must preserve 36,000 tokens for deterministic terminal closure
plus the Predictor; insufficient Signal/routing budget ends adaptive research and
locally freezes the current state as final without another model call. The closure
preserves hypotheses, beliefs, evidence provenance, contradictions, and question
classifications exactly; only `decision` and `next_information_needs` change.
Insufficient post-hoc budget preserves the immutable prediction and
fitness and writes a deterministic `budget_skipped` reflection.
Routing payloads never expose prior document fingerprints or content hashes. They
carry only remaining compact cards and prior compact Signal conclusions needed for
semantic complementarity; executed-ref removal and fingerprint no-op are local
deterministic controls. The canonical model payload names and emits those frozen
available cards first, before case-dynamic needs/results, to increase provider
prefix-cache reuse while retaining them as untrusted user data.

The v7 contract additionally freezes `predictor_context_bytes=24000`. Predictor
assembly removes repeated full Basic projections and full per-round Signal evidence:
it sends a Basic source/DataGap index, the complete final ResearchState, compact
Signal state/interpretation/coverage rows, and exact material only for final-state
Signal citation tuples. Complete source bundles and rounds remain in the local
trajectory. The compact payload is measured after anonymity masking with canonical
UTF-8 JSON and must fit its byte ceiling before provider request construction. This
keeps the byte-for-token preflight conservative and makes the 36,000 terminal reserve
internally consistent; no tokenizer approximation or post-call overflow is allowed.
Post-hoc compaction consumes that already-compact Predictor view directly: it preserves
the Basic `source_index` and `data_gaps`, final state, and compact Signal results while
omitting complete Basic projections and the full original Predictor context. It must
not reinterpret the Predictor `source_index` as a pre-projection Basic `requests`
bundle and silently emit an empty index.

A provider response that is not exactly one JSON object is a paid structured
output failure, not a process-level crash. The runtime persists its raw model
text and usage in a failure-only audit artifact, records the actual cost on the
attempt ledger, and does not add it to the valid-response cache. Role adapters
then treat the malformed text as invalid output under their already frozen
single structured-correction allowance. If the correction also fails, the
existing candidate/role failure semantics apply; no parser exception may abort
the whole round or advance a commit pointer.

Temperature is part of the exact request hash. Information Plan proposal calls
sample at `1.0`. Prediction, explanation, research, reflection, Signal
execution, and all other judge calls remain greedy (`0.0`). The runtime alters
temperature only, leaving nucleus sampling at its provider default.

Every structured role prompt includes its literal accepted JSON field contract.
The adapter validates and converts provider output at the role boundary before
domain construction; malformed shapes fail with a stage-specific
`ValidationError`, never a raw `KeyError`. The Information Plan proposer also
accepts the observed semantic `B/H_init/H_reflect/H_analyse` nesting as a
deterministic compatibility input, but durable Plan artifacts always use the
canonical flat field names. The literal canonical Plan contract is present on
every proposal call, including the first slot; provider responses that instead
use evidence arrays under `H_*` are rejected and retained in the exact cache,
not coerced into a bogus Plan.

Every role that receives source-derived text also receives the same explicit
untrusted-data instruction: source text cannot override the system message,
the output contract, identity/outcome boundaries, or source authorization.
Accepted free-text outputs from critic, round reflection, post-hoc, and proposer
are value-masked and rescanned against the complete 24-case alias inventory
before entering Plan/meta domains. Slow aggregate roles use a different boundary:
their case-derived inputs have already been masked and rescanned by the local
controller, so H1 must preserve the structured payload byte-for-byte rather than
recursively replacing Discovery-wide derived brands that can collide with source
types, enum values, Signal ids, or ordinary prose. Before send, H1 performs only
a non-mutating scan for strong exact identity terms. Free-text Mining/Update
outputs use the same strong-term scan and fail into the one bounded correction;
the leaking value is not echoed and accepted output is never silently mutated.
A fixed-semantics scanner rejects attempts to introduce probability thresholds,
redefine the six-month price surge/horizon, change the four-way judgment, or turn
`H_analyse` into a Predictor.

Signal Mining uses five narrow structured role stages rather than a
one-tool-per-turn Agent transcript:

- `signal_mining_hypotheses` proposes a portfolio of no more than three
  falsifiable hypotheses from bounded meta/backlog/Registry context;
- `signal_mining_case_ranking` ranks only allowed opaque case refs from
  label-hidden, identity-hidden company briefs for all hypotheses in one call;
- `signal_mining_contrast` supports/refines/rejects at most two locally feasible
  hypotheses from exact point-in-time positive/control evidence;
- `signal_mining_exploration_extract` creates label-hidden observable signatures
  for a locally selected diverse case batch; and
- `signal_mining_exploration_discover` reveals labels only beside those frozen
  signatures and emits supported candidates or refined patterns.

All stages use literal key/type contracts and one bounded correction. Creative
hypothesis/discovery calls sample at the run-contract proposal temperature;
ranking, extraction, and evidence contrast remain greedy. Exact request caching,
ledger charging, outcome/identity disclosure checks, and external-approval
semantics are identical to the other structured roles. The controller—not the
model—resolves case refs, performs positive/control feasibility, queries Raw
Info, stages candidates, executes fixtures, and selects issuer-disjoint
effectiveness cases.
H1 card projection omits `learned_profile` only when its exact stable version has
both zero `selection_events` and zero `unique_observations`; otherwise the full
anonymous profile remains visible. This removes repeated empty matrices without
discarding learned routing or effectiveness evidence, and never changes the
Registry/frozen-snapshot artifact.
The H1 provider contract is schema-only and contains no complete business-domain
hypothesis. If bootstrap `signal_need_items` are nonempty, the adapter requires
each hypothesis to share at least two non-generic, simply singular-normalized
topic terms with one exact need across its semantic fields. This is a grounding
check against supplied demand, not local hypothesis generation; failures receive
the existing one bounded correction and explicit empty remains valid.
H1 and the Plan proposer validate every proposed source type against the exact supplied
`available_raw_source_types` enumeration at the role boundary; aliases or
pluralizations receive the existing one bounded correction rather than becoming
a silently refined hypothesis or executable Basic-Info request.
For the Plan proposer, that enumeration is the deterministic semantic-family closure
of locally present or authorized Raw Info types over the frozen registered catalog.
Thus a local `filing` document makes the registered precision alias `10-k` usable,
while a type with no routable local or authorized family stays hidden.
If more feasible H1 hypotheses remain than the H3 per-cycle contrast budget,
the local controller records the untested reserve hypotheses as explicitly
deferred refined work so the next cycle sees them instead of silently dropping
them.
All H2/H3/E1 Discovery material is identity-masked before leaving the local
controller. Short ticker-like aliases remain case-sensitive in ordinary prose
to avoid masking common words, but are matched case-insensitively inside URLs;
short all-uppercase brands derived from a formal company name are masked too.
Each local case boundary compiles its expanded alias matcher once per payload
traversal and reuses it across every nested string. This is only a local
performance rule: the recursive mask, case rules, URL handling, and separate
post-mask scan remain mandatory and complete before request reservation or send.
It does not authorize a later full-Discovery-inventory rewrite of the aggregate
H1/control payload.
If H2 profile acquisition returns `provider_error`, `quota_deferred`, or
`materialization_failed`, the CLI records a cycle-level Slow data pause containing
only the opaque case ref and reason, leaves round/cycle pointers and Registry
unchanged, and exits 75. Resume uses the same frozen contract; the failure never
becomes model correction, candidate rejection, or Plan fitness.
Before H1, runtime performs a side-effect-free H2 profile preflight over the
same deterministic scan universe. Once that universe is intrinsically large
enough for the H2 total and class minima, runtime checks local point-in-time
readiness and the exact profile request's available authorized adapter capability; it does
not query, reserve, acquire, or materialize data. If local rows cannot meet the
H2 minimum and acquisition is impossible, runtime pauses at
`profile-preflight/profile_adapter_unavailable` before spending an H1 attempt.
A positive adapter capability does not predict provider success. During the
real H2 build, scanning stops as soon as the 32-row target and both hidden class
minima are satisfied; the 96-row scan limit remains only a deterministic upper
bound.

The proposal contract also states and validates the fixed market-backbone
invariant from the Information Plan spec. A proposed `B` must contain a compact
`market_data` request with at most a 60-day lookback and one document. The
runtime rejects and corrects a proposal that omits it; it does not silently add
or rewrite model-produced Plan content. This invariant prevents news-provider
quota exhaustion or unavailable filings from making every otherwise complete
case evidence-free, while leaving price-surge labels hidden and leaving Binary
F1 unchanged.

The Signal-result adapter also enforces the canonical unavailable-state
invariant. If a provider returns `state.value=unavailable` with a looser
coverage value, the boundary conservatively narrows coverage to `unavailable`;
it never promotes an unavailable state to partial or sufficient evidence.
Before validation, a cited span whose only mismatch is character case may be
canonicalized to the source text only when it has exactly one case-insensitive
match inside the cited document. The adapter copies that complete substring
from Raw Info; it never fuzzy-matches, changes the document id, or resolves an
ambiguous match. Every other exact-span failure uses the normal single model
correction and strict validator.

The fixed Blind Predictor prompt must state the Stage-1 unit as explicitly as
the evaluator: `2x` means the target security's adjusted share-price outcome,
using the prediction-time five-complete-trading-day adjusted-close mean as the
baseline and the maximum five-complete-trading-day mean inside the following
six calendar months as the future numerator. Revenue, earnings, users,
production, and other operating measures are evidence about possible price
repricing; none is itself the `2x` target. The prompt must not let a model reject
a price-surge hypothesis merely because an operating metric is not forecast to
double. It must frame the output as a forecast under uncertainty rather than a
proof obligation: an explicit future price target, certainty, or guarantee is
not required. `candidate_judgment=likely` or `possible` means that the supplied
evidence makes the security an evidence-backed opportunity candidate for the
defined price outcome. `possible` is a screening judgment: it does not require
more than 50% event probability, a quantified valuation bridge, or a proven
path to `2x`; a source-backed combination such as expectation-changing
acceleration, a material catalyst, or early market confirmation may qualify.
`unlikely` and `insufficient_information` map to the canonical negative
prediction. Positive judgments require a magnitude class, while negative
judgments require null magnitude. The prompt also discloses that the evaluation set is
outcome-stratified and not representative of the live-market base rate, but it
does not disclose exact cohort counts, require a positive quota, or couple
separate predictions. The four-way schema and deterministic mapping are fixed
framework semantics, not evolvable Plan content or case-outcome disclosure.
The active Predictor makes no dedicated token-probability request and persists
no `P(YES)` or decision-margin fields.

The Predictor adapter must persist the exact four-way `candidate_judgment`
alongside its binary projection and reject an inconsistent pair. Once truth is
revealed, the framework derives the fixed eight-case
`candidate_judgment_feedback`; both the post-hoc Predictor reflection and Plan
critic must receive it explicitly. The roles may use it to diagnose conservative
positive calls, overconfident mistakes, or evidence-coverage gaps, but they may
not rewrite the saved judgment or treat one realized outcome as proof of an
ex-ante probability category.

After truth reveal, the framework computes `prediction_outcome.correct` from
the immutable saved prediction and deterministic truth, including magnitude for
a true positive case. The reflection role receives that fixed bit and may
explain calibration or Plan failures, but model-authored disagreement cannot
overwrite it.
For a framework-correct case, the accepted post-hoc output must preserve at least one
specific `decision_drivers` item explaining which supplied evidence or counter-evidence
made the saved judgment work. An otherwise all-empty correct reflection receives the
bounded correction instead of entering the original case layer and later allowing a
generic vertical or horizontal summary to substitute for the case-level reason.
For a framework-incorrect case, at least one concrete item must appear in
`why_prediction_failed`, `misleading_signals`, `ignored_evidence`,
`missing_information`, or `plan_issues`. A false prediction with all diagnostic
arrays empty receives the same correction and, if still invalid, the existing
explicit validation-failure fallback rather than a content-free reflection.

The Plan critic must not receive complete saved trajectories. Its request uses
one deterministic compact row per case containing only an opaque case index,
stop state, prediction, ground truth, candidate-judgment feedback, post-hoc
reflection, and compact Signal id/version/state/interpretation/status summaries
with evidence counts. It excludes company/case identifiers, Basic Info, initial
and final research context, literal evidence spans, prediction paths, and usage
records. This preserves decision-calibration and Plan-failure evidence while
preventing the 24-case batch from repeating Raw Info into a provider request.
The same request includes deterministic comparisons against the candidate's
actual parents: parent Plan content, aggregate cohort metrics, a structured
Plan-field diff, an opaque source snapshot hash, and a same-snapshot flag.
Confusion/F1/precision/recall deltas exist only when that flag is true. The
round-reflection request receives the same comparisons keyed by new Plan id so
cross-generation lessons can reach FIFO meta-info even though historical seeds
never enter the current Plan Archive.
Round reflection receives compact record summaries rather than serialized
trajectories: Plan content, aggregate metrics, Plan-critic output, Signal-usage
counts, fitness eligibility, and evaluation stage/count/snapshot/cohort
metrics. It excludes embeddings, case ids, trajectories, Raw Info, research
contexts, and per-case labels. Horizontal reflection requires at least two newly
completed child Plan records. If only one Plan survives the round, the runtime
makes zero `H_R` calls and appends a deterministic empty horizontal layer with
that Plan's evidence ref; the complete original and vertical layers still commit
unchanged. This prevents a one-record role from merely paraphrasing the vertical
critic as a fictitious cross-Plan pattern and saves the redundant request.
After that call returns, the local runtime deterministically composes the final
`RoundMetaEntry`: original anonymous case reflections first, exact Plan-critic
and parent-comparison layers second, and the returned horizontal Round
reflection third. Neither the Plan critic nor Round reflector is asked to
reproduce an earlier layer. The proposer receives these complete committed FIFO
entries with outcome scanning enabled only for this retrospective meta-learning
role; request construction still fails closed on identity-bearing or source-
context fields. Its bounded original-layer samples choose the richest reflection
within each assessment class, not the first occurrence, so concrete case-level
failure attribution remains visible beside exact vertical and horizontal layers.
Legacy horizontal-only entries remain valid inputs.
Candidate-judgment feedback remains reflection-only: fitness and cumulative
Top-K selection continue to use Combined Binary F1 alone.

Preflight and dry-run never perform network I/O. LLM external mode additionally
requires an explicit acknowledgement equal to the frozen contract hash. Source
data is controlled independently; when disabled, a local resolver miss records
`external_not_authorized` and performs no network I/O.
An enabled data policy requires non-empty provider, capability, and source-type
authorization fields plus positive per-cycle and whole-run ceilings. The
broad-research profile stores `*` as the sole value in each authorization field,
meaning every historical adapter registered by the contract-bound code
revision; it does not turn an unsupported source type into a synthetic result.
A custom restrictive policy stores explicit names instead. The operator must
enable either policy once in the frozen contract and again for a resume
invocation; a request to execute data calls outside the frozen policy fails
explicitly rather than being silently ignored.
When the contract enables data acquisition but the current invocation omits
that second authorization, the cycle pauses before creating or resuming an
active cycle, sampling an evaluation snapshot, or resolving any case. It must
never reinterpret `external_not_authorized` as evidence that a Random case
lacks data and rotate the evaluation cohort. Contract-level authorization
absence is control-plane state, not a label-free data-readiness observation.
A disabled data policy has empty allowlists and zero ceilings; partially filled
but disabled policy data is rejected instead of being retained as ambiguous
latent authorization.

At execution time, before Plan proposals, the runtime materializes both the
fixed label-free market backbone needed by the evaluation evidence gate and the
inputs declared by the complete frozen Signal Registry. It uses
`SignalExecutor.prepare_inputs`, so readiness and later Signal execution share
the exact request construction, alias matching, authorization, acquisition,
append, re-query, and lineage path. Local Raw Info is always reused first. On a
miss, authorized adapters are tried in frozen catalog order within the same
source-data ceilings. A case is ready only when the market backbone and at
least 80% of stable Signal refs resolve. A new Random snapshot may skip
unavailable candidates while preserving its exact label and issuer constraints;
the fixed Anchor and an existing snapshot remain immutable. The readiness call
receives no ground truth, cohort name, or Locked Test content.

Information Plan proposal output contains only `B`, `H_init`, `H_reflect`, and
`H_analyse`. Runtime owns deterministic Plan ids and the exact selected-parent
lineage; provider-supplied ids are ignored. The provider receives an explicit
constraint that its four-field content must not exactly copy a selected parent,
plus a deterministic change focus keyed by proposal attempt. Exact-parent
content is validated inside the proposer adapter. The change focus is an enforced
content contract rather than prompt advice: a `B/H_init`, `H_reflect`, or `H_analyse`
attempt must differ in that exact field group from every selected parent, and a
change elsewhere cannot satisfy it. Exact copies and ignored focuses receive the
same one correction request with the failed output and precise validation message
as malformed content. Fixed-semantics scanning distinguishes explicit prohibitions
such as “without calculating probabilities” from affirmative probability/threshold
instructions and returns the matched prohibited phrase in correction feedback. The
literal words `threshold` and `cutoff` are not violations by themselves: retrospective
prose may explain that evidence stayed below the fixed doubling threshold. They are
rejected only when paired with an instruction to set/use/change a threshold or an
explicit replacement numeric threshold; probability/odds instructions remain blocked. The
outer candidate-attempt loop remains a separate bounded sampling layer; it must not
retry an exact duplicate without explaining the required change. An unrepaired
candidate is rejected as a bounded event without committing a partial round.

The proposer output contract names the exact JSON keys, value types, and role
substance without embedding copyable executable `B` or `H_*` candidate values.
Legacy example echoes, phrases such as `complete ... instructions`, and generic
template wording remain invalid. The proposer also validates role substance:
`H_init` covers hypotheses and unresolved needs/questions; `H_reflect` covers
evidence-based updating and the next-needs/continue/finalize decision; and
`H_analyse` covers evidence organization/weighting and counter-evidence or
uncertainty. This semantic completeness gate runs before parent/focus comparison,
uses the existing single correction, and names every field that must change.
Initial and correction requests share one byte-identical system prompt. Their
user payload contains one stable `proposal_context` followed by
`validation_feedback`, which is null initially and contains the rejected output
and exact local error only on correction. This retains all correction context
while preserving the largest provider-cacheable prefix.

The Research Controller's `continue/finalize` vocabulary governs information
collection, not the final opportunity class. Proposed `H_init` or `H_reflect` text
that defines or asks the controller to finalize an alternative prediction ontology
such as `strong up/up/down/strong down` is rejected through the same proposal
correction. Explicit guard language that preserves that boundary, such as keeping the
fixed four-way judgment intact or proceeding without altering the Predictor ontology,
must not be mistaken for a replacement ontology. The fixed four-way Predictor remains
the only classification owner.

Each candidate slot may make at most three independently hashed proposal
attempts. Every structured runtime role receives at most one correction with
the failed output and validation message. Unrepaired initialization/prediction
failures terminate that candidate; non-fitness reflections degrade to explicit
deterministic failure records. Exact transport responses remain in cache for
audit, but a transport-cache hit is never treated as domain validation.

For ResearchState corrections, the role is told explicitly that every evidence
provenance item named by `validation_error` must either change to a valid visible
reference or be removed; an unchanged rejected item is not a correction. The
runtime still validates the complete returned state and does not silently delete
or synthesize evidence. `H_init` also receives a fixed boundary reminder that the
six-month adjusted-price-doubling outcome is the evaluation definition, not an
issuer target whose terms should be researched. For structured market JSON, it
must cite a complete visible row rather than constructing a shorter object from
selected fields.

The evaluation-boundary reminder also forbids asking for the fixed baseline date
or baseline price: those are runtime-owned definition inputs, not issuer evidence.

For v6 Basic-Info evidence, the controller must copy one byte-for-byte contiguous
literal from one supplied projection: it may not use ellipses, join distant rows,
reorder JSON fields, or paraphrase `exact_text`. A literal that occurs exactly once
across the visible projection set is deterministically assigned to that projection;
otherwise correction feedback names the exact `supporting_evidence[index]`, supplied
projection, and matching projection ids before the candidate fails closed.
Each Basic evidence claim must also be quantitatively supported by the literal refs
carrying that same claim: every numeric quantity in the claim must occur, after local
format normalization, in the union of those exact texts. Normalization includes exact
decimal scaling for an explicit adjacent thousand/million/billion/trillion word or
standard `k/m/mm/b/bn/t/tn` suffix, so `$1.6053 billion` is equivalent to raw
`1605300000`; it performs no rounding, tolerance, or inferred unit conversion. A claim spanning two market
endpoints may use two refs with the same claim; a lone beginning-balance literal cannot
support a beginning-to-ending decrease. Missing quantities receive one actionable
correction rather than being accepted merely because some literal exists.
Every numeric-bearing item in `current_beliefs` or `contradictions` must in turn copy
one accepted evidence `claim` byte-for-byte. The role can attach several literal refs
to that same claim for a real multi-span fact, split a composite assertion, or remove
unsupported numeric detail. Runtime never treats a matching number from an unrelated
claim as support. Hypotheses and question fields remain outside this assertion gate.
Evidence-transition identity is source provenance, not the explanatory `claim`.
For Basic refs, reflect may restate a claim while preserving the provenance tuple
because the exact literal remains present in the ref and can be revalidated. For a
new current-batch Signal ref, every numeric quantity in the claim must occur in the
union of exact Signal evidence items referenced by refs carrying that same claim.
For a deterministic Signal, a claim may instead copy the exact canonical numeric
form from `interpretation.summary`; local validation treats that validated derived
record plus the cited source evidence as support. Rounded percentages, converted
units, and new raw quantities absent from both remain invalid.
A retained Signal ref from an earlier batch must preserve its prior claim byte-for-byte:
the backing batch is no longer in the model-facing context, so allowing an unsupported
restatement would erase or invent the upstream finding. Missing quantities or a changed
retained Signal claim receive the same single actionable correction as other evidence
violations. Deterministic terminal closure does not restate any claim. The reflect
contract uses a dedicated Signal-ref example.
A complete canonical Signal ref carrying redundant legacy citation fields is reduced
locally to its five canonical keys before current-batch validation; local code never
invents a missing Signal ref, evidence group, or index.
Every model-facing Signal-batch row includes its exact versioned `signal_ref` in
addition to durable `signal_id` and `version`. An unversioned returned id is expanded
only when it uniquely identifies one result in that current batch.
The same reflect request includes a compact, deterministic
`signal_evidence_ref_catalog`: one row per current-batch `signal_ref` with its exact
valid zero-based `supporting` and `counter` indices. Index-validation feedback must
identify the precise `supporting_evidence[index]`, returned ref/group/index, and the
valid indices for that ref/group so the one correction is executable. The runtime
does not repair semantic index mistakes locally; an index outside the frozen catalog
continues to fail closed after the correction boundary.
H_reflect does not receive canonical SignalEvidence objects. Runtime projects each
current-batch result into a compact row containing state, interpretation, and indexed
normalized evidence text; document identity/hash and raw `exact_span` stay local.
Projection removes HTML and repetitive market `retrieved_at/source/symbol`, caps
each evidence text at 1,200 characters, and caps all current-batch evidence text at
8,000 characters. Evidence refs returned by the model are still validated against
the complete canonical batch, so this token reduction cannot weaken literal,
point-in-time, or provenance checks. A validated deterministic numeric Signal sends
its exact canonical `metric=value` interpretation instead of a clipped raw JSON
excerpt; H_reflect still cites the canonical local evidence index.
After that validation, H_reflect must distinguish an answered need from an
unanswered one instead of changing text merely because it adopted a new Signal ref.
An unanswered prior need may remain only byte-for-byte; forcing it to change would
invite a false resolution or a blurred paraphrase. An answered or partly answered
need must be removed or narrowed, with `resolved_questions` / `open_questions`
updated consistently. Runtime never rewrites a need or infers from evidence alone
that it was answered.
If the response does not reduce the need count, any changed need containing at least
90% of a prior need's normalized word set is a cosmetic continuation and receives
the one bounded correction. Thus the actual pattern “old question + given the
absence of ...” cannot pretend to be progress; the role must either retain the exact
unanswered question or make a genuinely narrower evidence-driven need.
Runtime also rejects an internally stale exact need when a newly added resolved
question contains the same ordered three-or-more-word content phrase after removing
question boilerplate and function words. That narrow consistency check catches an
actual response that newly resolved production-and-cost guidance while retaining the
same production-and-cost-guidance need. It does not compare evidence semantics or
force unrelated needs to change.
Directly decidable Signal-claim quantity errors and this need-transition error are
reported together before the one correction. Fixing a citation must not consume the
only correction and reveal an already-visible stale/cosmetic need afterward.
Every unavailable Signal is rendered to downstream models as a deterministic
coverage-only statement, never its free-form original interpretation; the latter
remains in the durable canonical result. Prompts explicitly forbid turning
unavailable into evidence of absence, a new belief, or a resolved question.
This is an independent local transition boundary rather than a side effect of the
need-progress guard. For every unavailable current-batch Signal, runtime rejects a
new `resolved_questions` item that names the Signal topic and rejects a new
`current_beliefs` item that names the topic together with absence/unknown/unavailable
language. Open questions and hypotheses may still name the missing capability; a
coverage gap is allowed to remain an explicit research uncertainty.
The already-supplied `research_state.supporting_evidence` array is the canonical
indexed inventory for previously accepted refs and is not duplicated into another
context block. Tagged-ref shape validation occurs before domain construction and
names the exact output index, missing fields, unexpected fields, and expected Basic
or Signal field set. The single correction feedback aggregates all array-item shape
errors plus Basic claim-quantity mismatches that can be determined directly from
the returned claim/literal fields; an already-visible second defect cannot be hidden
until after the only correction is consumed. A retained Basic ref must copy its prior `projection_id` and
`exact_text` byte-for-byte while only `claim` may change. A retained Signal ref must
copy its prior `claim`, `signal_ref`, `evidence_group`, and `evidence_index`
byte-for-byte. Correction may instead remove either ref. Missing provenance is never
inferred locally.

LLM Signal execution does not serialize its complete resolved Raw Info
documents into the provider request. It receives the Signal Library's bounded
literal-window projection with document hashes and source offsets; complete
documents remain local for request fingerprints and strict validation of the
returned evidence. `SignalResult` carries only the canonical conclusion,
interpretation, and source evidence rather than duplicating Raw Info.
Because fixed-width overlapping windows can begin or end inside a sentence, number,
or JSON transcript field, a model citation may not touch a projection edge when that
edge is not also the normalized source-document edge. The neighboring overlap remains
available for a complete clause; an edge-fragment citation receives one correction
and otherwise fails closed. This prevents a literal ending in values such as `$1,`
from being accepted and later completed by reflection as an invented quantity.
If a returned Signal quote is absent from its supplied projection id but occurs exactly
once across all visible projections, runtime deterministically uses that unique
projection for raw-span mapping, matching the Basic-ref rule. Zero or multiple visible
matches remain semantic ambiguity and fail closed; runtime never edits the quote.
For a quote touching an internal projection edge, validation feedback identifies the
supporting/counter index, rejected projection id, start/end edge, and overlapping
projection ids covering that source boundary. This makes the sole correction
actionable while leaving the complete projections unchanged and retaining model
responsibility for selecting one complete literal or returning unavailable.
The shared one/two-Signal role uses one dedicated batch output example and no
single-`SignalResult` "return exactly" example. Its outer row copies the supplied
versioned `signal_ref`; its inner `result.signal_id` copies the matching
`signal_spec.signal_id` without the `:vN` suffix, and `result.version` copies the
integer `signal_spec.version`. Identity validation feedback reports returned and
expected values for all three fields and repeats that exact mapping in the one
correction action. Runtime does not strip a version suffix or otherwise repair a
semantic identity mismatch locally.
The initial and correction calls use the exact same system prompt. That stable prompt
always explains how a sole correction consumes the optional `validation_feedback`;
the dynamic failed output, error, and required action are appended only after the
unchanged shared `source_projection` in the user payload. This preserves the complete
Signal specs, skills, projection coverage, and local validation boundary while making
the large common request prefix eligible for provider caching. Pre-send token/cost
reservation remains a cache miss, and actual hit/miss usage remains durable evidence.

Model outputs are type-strict at the role boundary. JSON booleans, arrays,
objects, numbers, and required fields cannot be replaced by truthy strings,
character-wise iterable coercion, or implicit coverage/state defaults. Signal
retrieval excludes refs already executed in the same case before one compact-card
selection request. An empty ref array is a valid no-new-Signal result; a
conservative pre-acceptance check rejects empty once when a need contains an exact
three-or-more-word phrase from an available normalized Signal ref. It reports the
matching refs for model correction but never chooses one locally or applies fuzzy
matching. An unmatched empty result remains valid with no correction. A
malformed, duplicated, or out-of-card ref container receives the documented one
correction and then raises a usage-bearing candidate rejection if still invalid.
Neither path terminates the process with a raw container exception.

The selection request includes a bounded `research_context` built from the current
ResearchState's hypotheses, beliefs, contradictions, resolved/open questions, and
accepted evidence claims. It excludes evidence literals and provenance and carries no
revealed outcome. The selector uses this context only for applicability and
complementarity; the information needs remain the retrieval objective. This prevents
the selector from inventing a company stage that the controller state already
contradicts without duplicating the 32,000-character Basic projection.

Each later selection request also carries the deduplicated context tags from earlier
accepted selections in the same case. Version-owned exclusions are checked against
the union of these prior selector-authored tags and the current output's tags. Runtime
still never infers a tag from prose and never chooses a replacement Signal; it only
prevents the selector from dropping its own prior `mature_operations` classification
to bypass a later exclusion.

Routing tags remain non-semantic hints. Runtime normalizes strings, deduplicates
them, drops values outside the frozen tag vocabulary, and retains at most four in
model order. A model copying a visible card category such as `catalysts`, `risks`,
or `product` into `context_tags` therefore cannot reject an otherwise valid Signal
selection. A version-owned `routing_excluded_context_tags` list is the narrow
exception: if the selector attaches one of those tags to that same Signal, its own
applicability classification contradicts the visible card and receives the one
correction. Runtime never infers the tag or chooses a replacement Signal. Wrong refs,
missing fields, non-string tag containers, and invalid
reason/role enums retain their correction/fail-closed behavior.

Research initialization and compact routing also preserve provider-cache prefixes
across their single correction. The initial and correction system prompts are
byte-identical and always define an optional `validation_feedback`; the complete
stable role payload sorts before that field, which is null initially and contains
the failed output plus exact validator error only on correction. All evidence,
skills, needs, cards, learned profiles, and prior results remain visible, and local
validation is unchanged.

An all-`unavailable` Signal batch remains a durable trajectory/coverage event but
cannot change ResearchState under the coverage-only invariant. Execution therefore
skips `H_reflect` for that batch, retains the exact prior state, and routes again over
unexecuted cards within the existing guards. A mixed or available batch still calls
`H_reflect`; the shortcut never fabricates finalization or suppresses batch usage.

For a selected batch mixing deterministic and LLM Signals, deterministic execution
runs first and the soft subgroup runs second; successful subgroup results are merged
back into selector order before the ordinary whole-batch reflection. If the soft
request cannot pass its exact pre-send reservation, the completed deterministic
subgroup remains a durable partial round and can still receive reflection when it has
usable evidence. The trajectory then records `budget_exhausted` and stays ineligible
for fitness even if that bounded partial reflection returns `decision=finalize`.
An initial preflight failure performs no attempt/network action. If the initial soft
attempt completed but its correction preflight fails, runtime still counts that paid
usage while accepting no invalid soft result. In both cases the selection remains
auditable in the exact routing response and request-ready event.

When two LLM Signals share one deduplicated source projection, each compact Signal
entry lists its own `eligible_projection_ids`, derived only from that Signal's
resolved Raw Info documents. The role may read the shared projection once but may
cite only ids in the matching list. Mapping and validation enforce the same scope,
and correction feedback points back to that stable list. This prevents one Signal
from citing a document contributed only by its batch peer and avoids a predictable
paid correction without duplicating source text.

## Supervision, Interrupt, and Resume

The runtime emits structured, secret-free progress events before and after
request, cache, Plan, case, scoring, round-commit, and Slow-loop boundaries.
`slow_bootstrap` has no Fast boundary and therefore emits no
`fast_loop_started` event; its `slow_loop_started` rendering contains no empty
candidate-validation fields because those values do not exist until completion.
The workspace appends those events to its debug trajectory before forwarding
them to an optional caller callback. An external request interrupted after its
attempt reservation remains visibly `in_progress`; it is not silently retried
or marked unused.

One cycle freezes its mode, start round, configured Fast-round count, and input Signal
Registry version/hash in `cycle_state.json`. Resume calculates remaining Fast
work from the authoritative `state.json:last_completed_round`, not from files or
printed output. Slow validation is written as an exact immutable artifact before
Registry mutation. The exact transition is idempotently completed, the final
Slow result records input/output version/hash, and only then may the cycle
pointer advance and make that output the next cycle's input. The continuous CLI
supervisor may start successive bounded cycles, but `Ctrl+C` stops at the
current durable boundary without changing the frozen run contract, attempt
ceiling, cost ceiling, dataset, or Locked Test posture. It may leave only a
recoverable in-progress Signal transition, never an untracked partial rollover.
For `slow_bootstrap`, the frozen Fast target is zero, the round pointer remains
unchanged throughout, and the same Slow-validation/result order governs cycle
completion.

The stable operator launcher treats Python exit status `75` as the only
automatically recoverable process outcome. For an invocation-specific window
that defaults to ten hours, it relaunches the same `run-loop` after bounded
exponential delays from five to sixty seconds. Exhaustion of the wall-clock
window returns the same temporary-failure status for later manual resume. Any
other exit status, including `Ctrl+C` status `130`, propagates immediately.
Relaunch never edits the contract or pointers and cannot bypass frozen attempt,
cost, data-request, or Locked Test controls.

A shared evaluation-data failure is a control-plane condition, not candidate
validation. It is detected before Plan calls whenever possible and is persisted
as a non-authoritative shared-data pause diagnostic rather than an immutable
round rejection. If every attempted provider failed transiently, it exits with
status `75`; deterministic Anchor or ready-capacity infeasibility exits
terminally with its exact unavailable cases/reasons. In neither case may the
CLI return success or advance round/cycle pointers.

When no candidate is fitness-eligible, the runtime persists a deterministic
round-rejection checkpoint and capability-gap aggregation, emits a paused
status, and leaves both authoritative pointers unchanged. Resuming the same
immutable contract returns the same pause without repeating external calls.

External readiness and exhaustion are not candidate outcomes. Missing API-key
readiness, an absent/mismatched contract acknowledgement, and attempt/cost
ceiling exhaustion propagate as structured control-plane pauses before any
round rejection can be written. General contract validation failures are also
rendered as structured CLI errors rather than uncaught tracebacks.

## Local Artifact Inventory

The inventory command reads the existing historical-case, source-document, and
adjusted-price JSON artifacts and records current path, SHA-256, byte size,
schema, counts, symbols, date ranges, and missing-price symbols. It explicitly
marks the legacy case label as incompatible with the current
`realized_max_multiple` contract.

When the compact adjusted-price input does not cover all case symbols, the
filter command incrementally scans the larger local archive and writes a hashed
case-symbol-only artifact without loading the multi-hundred-megabyte source as
one Python object. This is a local deterministic transform and performs no data
acquisition.

Inventory is not migration. Materializing an `EvolutionDataset` additionally
requires a reviewed definition of the six-month baseline/smoothing boundary and
a human-approved issuer-disjoint split manifest. Locked Test ids must remain
sealed from ordinary run inputs.

## Full-Market Case Expansion Proposal

The saved clean-universe and full adjusted-price archive may be transformed
offline into a larger case-library proposal before any new source acquisition.
This is a distinct path from reusing the 60-issuer legacy case artifact.

The expansion command must:

- require an explicit list of shared calendar prediction dates and compute the
  active six-month five-day-smoothed label independently at every date;
- evaluate baseline, forward-price, listing-date, liquidity, and adjusted-price
  integrity independently at each requested date; record every failed date and
  retain the issuer when at least one case is eligible;
- exclude each case whose prediction date precedes the recorded IPO/listing
  date, because pre-listing prices may belong to a reused ticker or a different
  historical security identity;
- deduplicate issuers by CIK when available and otherwise use a stable symbol
  identity;
- reapply a fail-closed normal-stock gate after loading the saved universe:
  resolved CIK, active common equity, supported US exchange, non-SPAC operating
  issuer, at least `$1m` pre-prediction average daily dollar volume at every
  admitted case date, and no extreme adjusted-price discontinuity over a label
  window;
- classify issuers into `<1.5x`, `1.5-<2x`, `2-<3x`, `3-<10x`, and `10x+`
  maximum-multiple strata across the requested dates;
- include every eligible deduplicated issuer by default, preserving the
  resulting natural stratum counts instead of applying a fixed issuer cap or
  outcome-enrichment weights;
- materialize the reviewed positive Anchor symbol/date list, deterministically
  match and freeze seven non-surge controls, remove every Anchor issuer, then
  split the remainder by issuer and selection stratum so no issuer crosses
  Anchor, Discovery, Evolution Validation, or Locked Test ownership; and
- retain at least two Evolution Validation issuers in a stratum whenever four
  or more eligible issuers exist, while retaining at least one Locked Test
  issuer, so a rare Random label does not rotate dates from only one company;
- record source hashes, exact prediction dates, selection mode,
  available/selected strata, exclusions, seed, and the eligibility boundary.

This is a label-aware retrospective dataset-construction step. Outcome labels
define strata and support issuer-stratified ownership, but they never select a
smaller default library and never enter Raw Info or prediction requests. The
Fast loop separately imposes its exact Anchor `7/5/3/1` plus Random `3/2/2/1`
mix, so development F1 is still a controlled comparison metric rather than an estimate of live-market
prevalence or expected returns. A direct library call may request an explicit
smaller stratified cap for bounded fixtures or diagnostics, but the operator CLI
does not expose that legacy production default and the proposal records the cap
as `stratified_cap`.

The command writes immutable proposal artifacts only. It performs no external
calls, does not approve the proposal, and does not expose Locked Test to an
ordinary evolution run. New filing/news/profile acquisition begins only from a
reviewed exact issuer manifest, never by indiscriminately fetching the full
listed universe. It also emits a label-free acquisition scope containing only
company/CIK/ticker identities and required as-of dates. Data backfill jobs may
consume that scope without learning outcome strata or split ownership.

The v5 approval command accepts only the expanded proposal schema with its
machine-verified normal-stock gate. Before writing an approved manifest it
rechecks the Anchor and Evolution Validation hashes and runs the exact
`7/5/3/1` Anchor plus `3/2/2/1` Random feasibility preflight. A legacy or
Anchor-free proposal can remain audit evidence but cannot acquire a misleading
`human_approved` status under the current runtime.

### Historical Identity Decisions

An expansion may optionally consume one
`expanded-case-identity-decisions-v1` artifact when local listing metadata is
known to contain a stale ticker, missing CIK, or reused security identity. The
artifact is itself proposal input, not dataset approval. It must contain:

- a canonical `decision_hash`, review status, and unique decision ids/symbols;
- an `exclude` or `set_cik` action;
- an inclusive date range covering every requested prediction date;
- at least one immutable official SEC filing URL published no later than the
  earliest requested prediction date, plus a concise observed fact; and
- no outcome, return, stratum, or split ownership field.

`set_cik` is applied to the clean-universe listing before issuer ids and CIK
deduplication are computed. `exclude` removes the symbol from eligibility before
stratum allocation and records an explicit identity-decision exclusion. Neither
action edits the source universe or an older proposal.

The decision artifact identity participates in the proposal source-inventory
hash and is copied into the manifest audit inputs. An agent-proposed artifact
may create a new proposal, but the manifest retains a blocker requiring human
review of that exact decision hash before dataset approval. This allows obvious
source corrections to be evaluated without silently converting them into
approved research facts.

## Dependencies

Uses the top-level `llm` model registry for provider construction and the
evolution module's fixed priors and Signal snapshot hashes. Provider-specific
transport logic remains under `llm`; this module owns only evolution-run
governance.

The read-only local dashboard builder is described in
[`evolution_dashboard.md`](evolution_dashboard.md). Runtime code refreshes its
data bundle only at status, completed-round/cycle, pause, and interruption
boundaries; the HTML itself never becomes a state authority.

## Testing

Cover secret-free canonical contracts, exact replay/conflict rejection,
request hashing, predictor leakage scans, preview no-network behavior, exact
cache reuse, durable attempt/cost reservation, stale in-progress attempt
visibility, structured progress events, cycle-level remaining-round recovery,
exact Slow-validation and transition recovery, cumulative historical Plan
selection across Registry versions without reevaluation, local artifact
inventory, missing paths, and Locked Test sealing.
Full-market expansion tests additionally cover fixed-date labels, incomplete
case exclusion with eligible-issuer retention, CIK deduplication, deterministic weighted/diversity sampling,
issuer-disjoint stratified splits, hashed official-source identity decisions,
date-bound CIK replacement/exclusion, immutable replay, and zero external calls.
