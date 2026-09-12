# Evolution Runtime Control Plane

## V8 Slow execution additions

Only `evolution-run-contract-v8` may create new Slow self-evolution workspaces.
It adds finite `slow_only`, a committed history manifest hash,
`max_slow_cycles`, `min_new_signals_per_cycle`, reflection/source-read limits,
and semantic-review identities. V7 and earlier workspaces remain immutable
audit inputs and cannot be resumed under v8 semantics.

The contract freezes one outcome-independent issuer-level sampling protocol and
the role scopes for Slow source resolution. Request/cache identities bind the
actual memory projection, source manifest, exact Signal catalog, sample/corpus
manifest, protocol version, model, and relevant configuration. A newly committed
fact or lesson changes downstream identities; an exact replay does not create a
duplicate reflection or lesson.

## Status

Ready - v6 bounded-context, evidence-reference, and cumulative Signal-transition contract specified

## Purpose

Own the non-evolvable run boundary around the Information-Plan/Signal dual
loop. This module does not decide research strategy and is not part of the four
fields in an `InformationPlan`. It freezes inputs, discloses external requests,
enforces attempt/cost ceilings, caches exact responses, and composes the
bounded Fast/Slow execution runtime. Dataset inventory, migration, proposal,
and approval belong to `evolution_dataset.py`; this module re-exports its
existing command-facing functions so the CLI boundary remains stable.

The implementation is layered in dependency order:

```text
evolution_settings / evolution_dataset / evolution_transport
-> evolution_output_validation / evolution_research_validation
-> evolution_plan_roles / evolution_signal_roles
-> evolution_control
-> evolution_runtime (stable import facade)
```

New implementation code imports the owning module directly. The facade exists
only to preserve the established command and test import surface; it owns no
business logic.

Structured role validation is an execution contract. New validators emit
machine-readable `ValidationIssue` records; correction feedback and scoped
projection consume those records directly. Stable item ids may relocate a
corrected list item after provider reordering, while unrelated valid siblings
remain byte-identical and the complete original parser always runs again.
Diagnostic prose is never parsed to grant write authority. Legacy validators
without structured issues may still request a whole-object correction, but
cannot use scoped projection until migrated.

Signal routing, Exploration E1, Signal Update, and baseline-sensitive Predictor
checks emit the same issue contract. Optional routing quarantine may preserve
valid siblings only when at least one validated selection remains; removing the
entire invalid portfolio is an execution failure rather than a domain `no_match`.

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

Only `evolution-run-contract-v8` may execute. Older frozen contracts, including
v7, remain
readable for status/audit commands but run commands return
`legacy_contract_read_only`; no missing evaluation field receives an implicit
default. Before the first cycle creates requests or execution artifacts,
runtime verifies the exact Git revision, Python runtime, dataset hash, initial
enabled-Signal snapshot, historical Seed Pool manifest, and oracle id. On later cycles it verifies the current
stable snapshot against the last committed cycle output, not against the
initial contract snapshot. Evaluation snapshots are immutable recovery inputs
under the run workspace. Their existence does not prove round completion or
advance `state.json:last_completed_round`.
For v8, both model roles, code/runtime identities, and every consumed limit are
mandatory and type/range validated when the contract is loaded. Execution uses
those exact fields and never substitutes Python-side defaults.
The contract additionally freezes the fixed Predictor-semantics hash, the
available Basic-Info source-type catalog hash, a four-Signal/two-LLM-Signal
per-round ceiling, a 64,000-token terminal-plus-Predictor reserve for newly frozen
contracts, all
model-facing character ceilings, and role output-token ceilings. The frozen
role ceilings are 2,000 tokens for routing, Predictor, post-hoc, and H2;
4,000 for proposer, critic, and one LLM-Signal batch; and 8,000 for controller,
H1, H3, and Update. Historical contracts with the former 2,000-token controller
or H1 ceiling remain readable and execute those exact frozen values; newly
frozen CLI contracts derive H1 from the canonical role-limit table rather than
duplicating a stale literal. Exact code/contract checks still prevent silently
resuming an existing workspace with different runtime limits.
V7 additionally freezes `cycle_mode`. `fast_then_slow` requires a positive
`plan_rounds_per_signal_cycle` and no bootstrap manifest. `slow_bootstrap` is
single-cycle and requires exactly zero Fast rounds plus the hash of
`slow_bootstrap/manifest.json`. Its immutable manifest has one of two explicit,
mutually exclusive source kinds:

- `rejected_no_match` contains only identity-masked, label-hidden
  `no_signal_match` needs aggregated from compatible next-round rejection
  artifacts and binds their source contract/rejection hashes; or
- `committed_fast` accepts exactly one compatible active cycle whose complete
  Fast range is authoritative in `state.json`, whose Slow validation/result and
  cycle pointer are still absent, and freezes the committed round meta,
  stable-projection Signal learning events, capability backlog, and every
  contributing checkpoint/Plan/meta hash. Its backlog is rebuilt through the
  same committed-trajectory path as an ordinary cycle: every terminal
  `next_information_needs` value receives a stable `need_ref` plus exact
  Plan/case, source-round, trajectory-fingerprint, original-text, and stop-reason
  provenance before capability-gap aggregation. Calling the gap aggregator
  without those extracted Signal needs is an invalid bootstrap because it would
  silently erase Fast demand.

For `committed_fast`, the active phase may be `fast_loop` immediately after the
last Fast commit or `slow_loop` after normal resume has recognized the complete
Fast range. These are equivalent bootstrap boundaries only while both staged
Slow validation and staged Slow result are absent; any persisted Slow output
still makes the source ineligible.

Both kinds bind the exact input Signal Registry. Runtime verifies the manifest
before creating a cycle. For `committed_fast`, it idempotently reconstructs only
the frozen post-pointer learning derivatives and in-memory meta view; it never
copies or invents a Fast pointer in the target workspace. Independent committed
cycles cannot be merged into one bootstrap. The mode changes only the Slow
trigger; H1/H2/H3, Update, validation, promotion, Locked Test, attempt, cost,
and source-data policies are unchanged.
Freeze additionally rejects an empty stable Signal Registry. The clean-worktree
check is scoped to runtime-bearing tracked paths (`src/`, `scripts/`, and
`configs/`) plus untracked files under those paths; unrelated progress or memory
notes do not make the executable HEAD unreproducible.

Seed discovery is local, deterministic, and performs no model or provider
calls. A first-ever evolution root produces a valid empty
`seed_pool/manifest.json`. If a manifest was durably staged before the contract,
freeze reuses and verifies it rather than rescanning newly completed history.
Every copied historical Plan must also satisfy the current code revision's full
provider-facing Plan contract before it can enter the seed pool, including
market-backbone, source-scope/ownership, fixed-semantics, and role-substance
validation. A legacy Plan that was valid under its source revision but is no
longer semantically valid is excluded rather than supplied as proposer context.
Loading a previously staged pool revalidates every copied Plan and fails closed
if current validation rejects one; it never silently repairs or rewrites the
immutable parent content.
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

The outcome-field scan is path-aware for one source-owned semantic field:
`evidence[*].structured_context.concepts[*].label` is the original SEC Company
Facts concept label already bound to a raw document span, not an evaluation label.
This narrow exception does not admit `label` at any other request path, and does
not relax identity or future-outcome scanning.

The post-hoc reflection boundary rescans the original anonymous context for
identity aliases, then treats the already validated immutable prediction and
numeric revealed truth as typed records. It does not rescan prediction enum
values as free identity text, because legitimate values such as confidence
`low` can equal a ticker alias (`LOW`).

Free-text scanning preserves alias type. Company names are matched
case-insensitively, while short uppercase ticker aliases are matched
case-sensitively. A bare two-character uppercase token is too ambiguous to prove a
ticker leak (`AI` is also ordinary domain vocabulary); a two-character ticker is
rejected only in explicit ticker context such as `$AI`, `ticker AI`, or
`NASDAQ: AI`. Three-to-five-character uppercase tickers retain exact
case-sensitive boundary matching. The current case's internal id, identity fields, source aliases,
composite formal-name components, suffix-stripped natural company names, and
distinctive leading brand tokens are independently stripped and masked before a
defense-in-depth scan of the assembled context. This still catches an explicit
`ticker AN`/`ticker LOW` leak but does not misclassify ordinary prose such as "an
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
The default frozen case ceiling is 256,000 tokens while the finalization reserve is
64,000. The reserve is derived from the bounded terminal H_reflect initial/correction
envelope plus the compact Predictor envelope under the same byte-for-token admission
metric; post-hoc remains optional and may use its deterministic `budget_skipped`
record. The ceiling is deliberately above ordinary reported-token use because
request admission conservatively counts one UTF-8 byte as one token. It must leave room
for the single correction of an admitted full 32,000-character soft-Signal batch after
H_init and routing, and for a ResearchState compaction correction after a two-round live
case; otherwise the initial paid calls can be accepted for transmission but their
promised bounded correction can never be sent. Raising this engineering ceiling does
not raise source-context, role-output, call-count, Signal-coverage, or cost ceilings.
Historical v7 contracts that froze the former 36,000 value remain readable immutable
evidence but cannot execute across the code revision; new freezes always write 64,000.
Adaptive research must preserve 64,000 tokens for any reflectable terminal batch
plus the Predictor. Once a completed batch reaches that reserve boundary, H_reflect
receives `must_finalize=true` and may consume the reserved terminal envelope; its
model-authored valid `finalize` remains mandatory. When an ordinary reflection
reservation cannot fit and a reflectable executed batch exists, retry once with
`must_finalize=true` and the remaining total budget, including the reserved
terminal envelope. Account for paid correction usage before that retry; preserve
the same prior state, batch and selection intents and run the unchanged complete
validation. If that terminal call cannot fit or validate, retain the failure and
ineligibility; never recursively retry or force a successful decision.
Insufficient routing budget, or
insufficient Signal budget
before any result exists, ends adaptive research with the current `continue` state
ineligible for fitness; runtime must not disguise missing research as finalization.
When a completed deterministic subgroup makes a partial batch reflectable but its
soft peer cannot pass reservation, the existing terminal-reflection contract
applies instead.
Insufficient post-hoc budget preserves the immutable prediction and
fitness and writes a deterministic `budget_skipped` reflection.
Routing payloads never expose prior document fingerprints or content hashes. They
carry only remaining compact cards and prior compact Signal conclusions needed for
semantic complementarity. A prior conclusion contains only Signal identity/version,
value/confidence, coverage, and bounded interpretation summary; its evidence arrays,
literal spans, document ids, and timestamps remain local. Executed-ref removal and
fingerprint no-op are local
deterministic controls. The canonical model payload names and emits those frozen
available cards first, before case-dynamic needs/results, to increase provider
prefix-cache reuse while retaining them as untrusted user data.

The v7 contract retains `predictor_context_bytes=24000` as a presentation target
in newly frozen code. Historical runs retain their frozen hard-cap behavior.
Predictor assembly removes repeated full Basic projections and full per-round
Signal evidence, but preserves the complete final ResearchState and every cited
Signal evidence tuple. Target overflow is visible in context metadata and is not
an independent candidate rejection. The exact wire-byte reservation plus output
must still fit the remaining case budget before transmission. Complete source
bundles and rounds remain in the local trajectory.
Post-hoc compaction consumes that already-compact Predictor view directly: it preserves
the Basic `source_index` and `data_gaps`, final state, and compact Signal results while
omitting complete Basic projections and the full original Predictor context. It must
not reinterpret the Predictor `source_index` as a pre-projection Basic `requests`
bundle and silently emit an empty index.

A provider response that is not exactly one JSON object is normally a paid structured
output failure, not a process-level crash. One transport-only exception is accepted:
if the JSON decoder uniquely parses a complete object prefix and the entire remaining
non-whitespace suffix is exactly one redundant `}`, runtime drops that delimiter and
records the normalization kind plus the raw-output hash in the valid response cache.
It does not repair fields or values. A second JSON value, prose suffix, more than one
delimiter, wrong closing delimiter, or incomplete object remains invalid. This bounded
normalization handles a provider envelope defect without spending a semantic correction
call and remains fully auditable.

For invalid structured output, the runtime persists its raw model
text and usage in a failure-only audit artifact, records the actual cost on the
attempt ledger, and does not add it to the valid-response cache. Narrow parsed
role adapters, including Slow H1/H2/H3/Update, then consume their already frozen
single structured-correction allowance using the exact parser failure and
unchanged task payload. They do not resend the raw malformed text: it is already
preserved locally, is not needed to regenerate the contract, can contain an
identity alias, and would duplicate paid context. If the correction also fails,
the existing candidate/role failure semantics apply; no parser exception may
abort the whole round or advance a commit pointer.

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
An empty or whitespace-only string in optional `B.requests[index].query` is the sole
field-level no-op normalization: runtime omits it before `RawInfoRequest` construction
because both forms authorize the same unfiltered target-company request. The exact
provider JSON remains cached; non-string queries and empty required fields still
require correction.
When proposal validation identifies raw `B/H_*` paths, correction feedback carries
the same numbered obligations used by other structured roles and those paths become
the only write scope. Runtime byte-compares the rejected and corrected raw objects;
fixing one `B.requests[index].query` cannot rewrite H_init, H_reflect, H_analyse, or
another request. A child-field authorization also preserves list shape; only an exact
element path may authorize adding or removing that element. Broad whole-Plan defects
with no mechanically narrow path retain the single correction without a false local
scope guess. A path inferred from validation prose is eligible for this write scope
only when its root and every existing ancestor resolve against the rejected JSON
object; a missing final child is allowed only for an explicit shape repair. Dotted
prose tokens, abbreviations, domains, and version-like text therefore remain
diagnostic prose and can never authorize mutation or prevent scoped projection.

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
Plan validation applies that boundary at the owning field rather than to the
serialized four-field object. `H_init` may discuss evidence that changes the
likelihood of an operating or commercial event; this is hypothesis formation, not a
replacement Predictor probability. `H_reflect` may decide only whether evidence
collection should continue or finalize and cannot decide which price direction,
trend, or outcome is likely. Each violation names its exact `H_*` path so correction
cannot rewrite the other role instructions or Basic requests.

Slow H1 explicitly binds each hypothesis to the fixed Discovery positive/control
comparison. Its expected pattern must name both groups using case/group/cohort
language, and its statement/pattern/falsifiers cannot introduce a later-quarter,
later-year, event-study, short-window market reaction, return, momentum, or
outperformance outcome that H3 will never evaluate. It cannot invent opaque case
refs or bracketed case placeholders. The statement must assert a measurable
cross-group feature rather than merely say that data are available, observable, or
inferable from a source. Cross-issuer patterns cannot use raw absolute revenue,
earnings, cash, production, cost, or similar scale as the discriminator; they must
normalize against a case-local expectation, guidance value, prior period, ratio, or
other comparable baseline. Before H1, local code resolves the bounded anonymous H2
brief pool and derives a label-free `h2_applicability_contract` from fields and values
that are actually present, rather than claiming that optional dataset fields are
visible. `applicability` is exactly one canonical, non-conjunctive screening rule:
`all_ready_issuers`, `business_description_topics:<term>|...`, or one observed-field
rule among `industry_values`, `sector_values`, `exchange_values`,
`market_cap_bucket_values`, `listing_age_bucket_values`, and
`raw_info_source_type_values`. A non-description value must come from the supplied
contract; business-description topics are bounded short terms. Free prose and
multiple-field conjunctions are invalid, so an H2-visible clause cannot conceal an
analyst-coverage, consensus, guidance, actual-metric, decomposition, market-data, or
classification prerequisite. Those document facts belong to the H3 query.
At least one falsifier explicitly names both fixed groups and states that absent
separation, overlap, or reversal would refute the hypothesis. Neither group may be
parenthetically or otherwise redefined as a candidate-specific result such as an
estimate beat, price move, or sustained growth; group membership remains the frozen
Discovery label. `query` is a concise two-to-eight-term retrieval topic, not an
imperative company screen, numeric threshold, or duplicate time window. Thresholds
belong in the feature/test and `lookback_days` owns the evidence window. After
generic-term normalization, runtime derives the candidate construct from the topic
terms shared by `hypothesis_id` and `query`; `expected_positive_pattern` retains at
least half of that construct, rounded up. This lets a pattern omit source qualifiers
while binding the fixed-group feature to the evidence H3 will retrieve; it rejects the
observed guidance-comparison and estimate-revision candidates whose patterns retained
too little of their shared construct. Runtime identifies the pattern path but never
authors a synonym or replacement. When applicability is invalid, correction feedback
identifies the unsupported form/value and requires complete replacement with one
supplied canonical rule. Existing
Signal exclusion compares the candidate identity and evidence query, not an existing
metric mentioned only as a downstream comparison or falsifier. H1 aggregates these
locally decidable issues into one validation message and uses a stable initial/
correction prefix. The generic fixed-semantics detector treats probability notation
only as a standalone `P(` token; an ordinary word ending in `p` before parentheses is
not a Predictor-semantic redefinition. Stable-identity topic normalization retains
the compact `yoy` qualifier after converting year-over-year spelling; otherwise the
specific `revenue_growth_yoy` identity would collapse into generic `revenue growth`.
Each H1 validation issue names the exact `hypotheses[index]` field or falsifier item
that must change. Diagnostic matched text stays inside that one issue rather than
creating another semicolon-delimited obligation. This makes the bounded correction
checklist field-executable without authorizing local hypothesis repair.

Output identity rejection must not consume the sole correction while hiding other
pure local validation defects in the same structured value. The adapter still sends
an empty invalid output and never echoes the leaking value, but it also runs the
side-effect-free role parser locally and appends its alias-masked validation message
to the identity path. A correction therefore sees every safe, locally decidable issue
at once without receiving the identity-bearing content.

Signal Mining uses four narrow structured model stages plus one deterministic local
H2 shortlist rather than a one-tool-per-turn Agent transcript:

Persisted cross-case reflections and prior-work prose are anonymized at the
Mining context boundary before the outgoing identity scan. Update evidence facts
remain exact source substrings without a per-fact character ceiling; transport
limits bound output size. Document identities are mapped to opaque refs before
text anonymization, consistently across current results and executed evidence.

- `signal_mining_hypotheses` proposes a portfolio of no more than three
  falsifiable hypotheses from bounded meta/backlog/Registry context;
- local `H2 canonical shortlist` applies each H1 rule to the same label-hidden,
  identity-hidden briefs, preserves their deterministic order, and retains at most
  the configured number of opaque refs; an empty shortlist means no brief matched;
- `signal_mining_contrast` supports/refines/rejects at most two locally feasible
  hypotheses from exact point-in-time positive/control evidence;
- `signal_mining_exploration_extract` creates label-hidden observable signatures
  for a locally selected diverse case batch. Each observation carries a supplied
  document ref and a byte-exact visible span; empty evidence permits only an empty
  observation list with a non-empty gap; and
- `signal_mining_exploration_discover` reveals labels only beside those frozen
  signatures and emits supported candidates or refined patterns, but only after
  both groups retain the configured count of locally grounded signatures. The
  controller may try at most one same-group evidence fallback per required slot;
  exact spans, not model-authored summaries, remain authoritative in discovery.
  The reveal prompt states that the supplied positive/control labels are now
  visible; a no-candidate rationale claiming they remain hidden or unavailable is
  a correctable semantic contradiction.

All model stages use literal key/type contracts and one primary bounded correction.
Current v7 contracts freeze `max_structured_corrections=2`: only when that first
correction still fails local validation does the role receive one final recovery
request containing the latest rejected output and freshly recomputed obligations.
Successful initial/first-correction paths make no additional call. Creative
hypothesis/discovery calls sample at the run-contract proposal temperature;
extraction and evidence contrast remain greedy. Exact request caching,
ledger charging, outcome/identity disclosure checks, and external-approval
semantics are identical to the other structured roles. The controller—not the
model—resolves case refs, applies canonical H2 applicability, performs
positive/control feasibility, queries Raw
Info, stages candidates, executes fixtures, and selects issuer-disjoint
effectiveness cases.
H3 feasibility is computed over the exact bounded excerpts sent to the model, not
over hidden remainder text from the source documents. Full-document query coverage
may be retained only as audit context. If the model-visible excerpts do not retain
the required distinct terms and short-range ordered-pair coverage, the case is
locally unavailable and no contrast call may claim that the model saw sufficient
evidence. Query topics of one or two normalized terms require every term; longer
topics require a 75-percent rounded-up supermajority plus at least one consecutive
query pair in a short visible span. This treats modifiers such as `trajectory` or
`comparison` as retrieval vocabulary rather than an accidental all-terms Boolean
filter while still rejecting scattered or minority lexical overlap.
The former H2 LLM ranking/correction is retired: once H1 applicability is a
machine-decidable predicate over the actual brief pool, another model judgment adds
no evidence, can contradict that predicate, and repeats the largest Slow context.
H1 card projection omits `learned_profile` only when its exact stable version has
both zero `selection_events` and zero `unique_observations`; otherwise the full
anonymous profile remains visible. This removes repeated empty matrices without
discarding learned routing or effectiveness evidence, and never changes the
Registry/frozen-snapshot artifact.
The H1 provider contract is schema-only and contains no complete business-domain
hypothesis. If bootstrap `signal_need_items` are nonempty, the adapter requires
one through the supplied hypothesis limit rather than accepting an unexplained empty
portfolio, and each hypothesis must share at least two non-generic, simply singular-normalized
topic terms with one exact need across its semantic fields. This is a grounding
check against supplied demand, not local hypothesis generation; failures receive
the existing one bounded correction. Explicit empty remains valid only when no
`signal_need_items` exist.
The same parse boundary rejects a renamed hypothesis when its semantic text
contains the complete multi-term id of a stable Signal or registered
deterministic function supplied in the request. Prompt advice alone is not the
duplicate guard.
When one H1 portfolio item fails but other hypotheses are not named by the
aggregated validation error, correction preserves every unmentioned hypothesis
byte-for-byte and changes or removes only the named invalid items. With nonempty
`signal_need_items`, an empty correction cannot erase otherwise valid portfolio
work. This keeps the correction local to its diagnosed defect instead of making
independent hypotheses share one all-or-nothing fate. If the rejected value is
withheld from correction feedback because it leaked a protected identity, runtime
cannot compare correction bytes and instead reapplies every semantic validator to
the replacement; it never weakens the identity boundary merely to enforce scope.
The fixed-group mention check recognizes the same bounded label aliases on either
side: `positive/control cases|groups|cohorts`, with optional `fixed` and/or
`Discovery` qualifiers immediately beside the label. Thus ordinary wording such as
`positive Discovery cases` is not mistaken for an absent group, while a bare
`positive` adjective or a newly authored membership definition still does not pass.
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
`profile-preflight/<stable-unavailability-reason>` before spending an H1 attempt.
Known SEC configuration absence is reported as
`sec_user_agent_unconfigured`; no contact value is persisted or printed.
A positive adapter capability does not predict provider success. During the
real H2 build, scanning stops as soon as the 32-row target and both hidden class
minima are satisfied; the 96-row scan limit remains only a deterministic upper
bound.
H2 output is not an unexplained opaque-ref list: every selected ref includes a
`profile_evidence` span of 1-160 characters copied from its supplied anonymous
brief and an `applicability_reason` of 1-240 characters. The reason must state
positive visible support for material applicability; language that admits missing,
insufficient, generic, or unconfirmed support invalidates the inclusion instead of
turning an inapplicable case into a ranked case. Inferential language such as
`suggests`, `indicates`, `aligns`, `likely`, `typically`, `may`, or `might` also
invalidates an inclusion when it substitutes an assumed profile fact for visible
support. The adapter aggregates all locally decidable span, bound,
self-disqualification, and inference defects into the one correction before
returning only the ranked refs to the local label-owning controller; empty
per-hypothesis selections remain valid. Its output contract is schema-only and
contains no case ref, hypothesis id, evidence phrase, or business reason that can be
copied as if it came from the supplied brief. The locally persisted rejected H2
value is not echoed into the correction; the unchanged hypotheses/briefs plus the
aggregated validation categories and affected opaque refs are sufficient, preserve
the cacheable prefix, and avoid paying to resend a padded ranking.
The initial and correction requests use one stable provider prefix with
`validation_feedback=null` on the initial request so the repeated H2 pool remains
cacheable.
For H3, exact source routing is followed by an ordered query-coverage gate. Longer
queries require rounded-up 75-percent distinct non-generic query-term coverage
across the model-visible packet, including at least half of the topic's consecutive
pairs rounded up within bounded document excerpts.
Excerpt anchors and window scores share the gate's complete-term
normalization and ordered-pair semantics; raw substring frequency is not evidence
relevance. H3 has an explicit
`inconclusive` decision for residual semantic evidence insufficiency; it is persisted
as evidence-unavailable and cannot become refinement, rejection, or candidate state.

All Slow output and candidate contracts are schema-only, including H3 decisions,
E1 signatures, and Update decisions/fixtures; no populated answer or business
example is included. H1 is instructed to retrieve a direction-neutral information
topic that can serve either fixed group, leaving feature direction to H3 rather
than requiring it in every source. Update rationale must cover every supplied
opaque induction ref under the normal correction budget. This checks traceability,
not semantic truth; actual case-specific reasoning remains an explicit live audit.
Mining supplies its exact visible-evidence selector to the shared resolver before
the document limit. Query-matched packets are preferred; exact-source comparator
packets are retained and explicitly marked unmatched rather than mislabeled as
missing data or as proof of absence. Unless both fixed groups contain direct
query-matched packets, H3 is constrained to `inconclusive`. Update induction uses
the execution batch's existing resolution, never a new Mining request; all exact
input hashes and the partial-excerpt boundary are retained for content audit.
If the hypothesis path has no candidate because it has no usable proposal/evidence
or only inconclusive H3 decisions, the production adapter executes the existing
exploration track once in the same Slow cycle. Its audit is nested separately and
both tracks retain the unchanged candidate and promotion gates; substantive H3
refinement or rejection is not overridden by this fallback.

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
For a positive judgment, the prompt requires at least one key reason to state the
source-backed positive candidate thesis; explicit counter-evidence belongs in
other reasons or uncertainties but cannot be the entire positive rationale. The
adapter applies a conservative cross-field gate only when every key reason contains
an explicit negation of the defined `2x`/doubling/surge/repricing outcome. It does
not classify ambiguous prose or require a fixed positive vocabulary. The one bounded
correction receives a generic alternative-path obligation over
`candidate_judgment`, `magnitude`, and `key_reasons`: it may switch to a valid
negative judgment/magnitude pair while retaining negative reasons, or retain the
positive pair and supply an affirmatively supporting reason. The complete parser is
rerun, and fields outside that alternative set remain byte-for-byte fixed.
When `prediction_baseline.status=available`, runtime rejects a Predictor reason or
uncertainty that broadly says market data is absent, unavailable, missing, or not
provided. The same check applies to every post-hoc diagnostic array using its retained
compact baseline. A model can still name missing forward estimates or other specific
inputs, but cannot erase the price data it actually received and thereby manufacture
a data-gap lesson.
Baseline validation distinguishes the supplied current mean from a mathematically
derived outcome threshold. If a reason places `Nx`, `N×`, `double`, or `twice`
immediately before the baseline phrase, the cited value is valid only when it equals
that multiple of the runtime mean within the same tolerance; it is not compared to the
mean as though it were the current price. Other baseline/current-price labels retain
the strict direct comparison.

Predictor semantic correction is path-scoped. When validation names one or more
`must_change_paths`, every top-level field outside those paths remains byte-for-byte
equal to the rejected object. For a named list item, all other old items remain in the
same order and the correction may introduce at most one replacement per named item.
Thus fixing one baseline reason cannot change `candidate_judgment`, magnitude,
confidence, session id, unrelated reasons, or uncertainties. The shared call-free
authorized-path projection may discard unrelated rewrites while retaining an exact
model-authored repair, followed by complete revalidation. Ambiguous indexed shape
changes and invalid projected objects still fail closed; runtime never authors a
reason or a judgment.

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
explicit replacement numeric threshold; action verbs match complete words, so the
market-data term `adjusted close` cannot be mistaken for an instruction to `adjust` a
threshold. Probability/odds instructions remain blocked. The
outer candidate-attempt loop remains a separate bounded sampling layer; it must not
retry an exact duplicate without explaining the required change. An unrepaired
candidate is rejected as a bounded event without committing a partial round.

The proposer output contract names the exact JSON keys, value types, and role
substance without embedding copyable executable `B` or `H_*` candidate values.
Validation is behavior-based rather than tied to captured historical responses:
phrases such as `complete ... instructions` and generic template wording remain
invalid, while no exact-output blacklist is maintained. The proposer also validates
role substance:
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
attempts. Every structured runtime role receives at most the frozen
`max_structured_corrections` value, currently two, with the immediately preceding
failed output and validation message. The second is a provider/model-agnostic recovery
path, not relaxed acceptance: the same parser, semantic validators, identity boundary,
correction scope, token/call/cost ceilings, and exact cache/ledger controls rerun.
Unrepaired initialization/prediction
failures terminate that candidate; non-fitness reflections degrade to explicit
deterministic failure records. Exact transport responses remain in cache for
audit, but a transport-cache hit is never treated as domain validation.

For ResearchState corrections, the role is told explicitly that every evidence
provenance item named by `validation_error` must either change to a valid visible
reference or be removed; an unchanged rejected item is not a correction. The
runtime still validates the complete returned state and does not silently delete
or synthesize evidence. Parser-shape errors may name the
returned key set for diagnosis, but an already precise semantic `ValidationError`
must pass through unchanged rather than being wrapped once or twice as if every
top-level ResearchState field were invalid. The correction contract requires every
actually named item plus any explicitly named linked assertion to change, and every
unrelated valid item to remain byte-for-byte. Quantity feedback therefore names the
evidence index and any identical `current_beliefs`/`contradictions` indices that must
track a corrected claim. `H_init` also receives a fixed boundary reminder that the
six-month adjusted-price-doubling outcome is the evaluation definition, not an
issuer target whose terms should be researched. For structured market JSON, it
must cite a complete visible row rather than constructing a shorter object from
selected fields.

Directly invalid paths and repair dependencies are distinct. When an H_init Basic
`exact_text` literal is over the output limit, the literal path remains the only
mandatory change. Correction feedback also emits bounded
`permitted_dependency_paths` for every same-claim evidence claim and byte-identical
belief/contradiction that could become invalid after the literal is shortened. Those
paths are not independently invalid and need not change when the shorter literal still
supports the claim; otherwise the provider may narrow/remove the same-claim evidence
and update/remove its linked assertion. Every path outside the mandatory and permitted
sets remains byte-for-byte. This dependency scope makes a repair executable without
predicting which shorter literal the provider will choose, while the unchanged
quantity/link validators reject unsupported or unrelated drift.

ResearchState evidence claims must be nonempty strings with grounded support.
A suggested 400-character claim length is not a parser or domain validity limit;
complete claims are retained unchanged. Empty-claim feedback identifies the exact
claim and identical linked assertions for bounded correction.

ResearchState is a compact decision frontier. Suggested compression targets are
`hypotheses=3`, `current_beliefs=8`, `supporting_evidence=8`, `contradictions=4`,
`resolved_questions=6`, `open_questions=6`, and `next_information_needs=6`, with
24 combined items, 300 characters per non-evidence item, 6,000 canonical JSON
bytes, and 800 characters per Basic literal. These are advisory, not evidence
validity criteria. Preserve complete supported assertions rather than truncating
or rejecting them solely for crossing a summary target. Existing request/output
and run budgets remain hard bounds; canonical claim shape, literal grounding,
quantitative support, PIT boundaries, and need ownership remain enforced.
An actionable retrieval question belongs in `next_information_needs`; an exact
byte-identical copy in `open_questions` adds no uncertainty state and is rejected at
the `open_questions[index]` path into the same aggregated correction. Runtime compares
only exact strings and never infers topical equivalence. H_reflect may preserve an
exact duplicate already present in a committed legacy state, but it may not introduce
a new one; new H_init states have no compatibility exception. This removes repeated
text from every later routing, reflection, Predictor, and post-hoc context without
silently mutating accepted state.
The provider contract states the ownership operationally: `open_questions` contains
only material uncertainty that is not itself an actionable retrieval question, and it
returns an empty array when every open question is already in next needs.

H_reflect receives observed counts and suggested remaining capacity as compression
guidance. Runtime does not reject otherwise valid research for exceeding those
targets. If JSON output is truncated at the frozen output-token allowance, the
existing bounded correction still applies. Initial and correction system prompts
remain byte-identical.
When the runtime must finalize and every nonempty batch result is unavailable by
value or coverage, H_reflect is deterministic: preserve every previous state field
and change only decision to finalize, with zero model usage. This does not infer
absence, answer a need, or consume unavailable content as evidence. Mixed or
nonterminal batches retain normal reflection and validation.
Every role correction also receives a deterministic `obligations` array alongside the
complete audit string and rejected output. Each row contains one numbered error segment
and the paths named by that segment; `obligation_count` makes partial repair directly
observable. Correction-only feedback also flattens those paths into one deduplicated
`required_change_paths` checklist with its exact count and a final comparison reminder:
every rejected value at a listed path must differ or be removed before return. This is
diagnostic redundancy for completion, not another correction or local repair. A
separate `permitted_dependency_paths` list, when present, authorizes only the bounded
linked fields that may become invalid because a mandatory evidence-literal repair
changes their support; it does not make them mandatory or open any unrelated field.
The projection does not interpret evidence, choose replacement content, or change
validation: the model must correct every row, and the same parser and local semantic
validators rerun after each contract-bounded correction. The shared correction
prefix contains only this role-neutral contract. ResearchState-only repair advice for
evidence quantities and claim-length/provenance coupling is appended only to
H_init/H_reflect; unrelated roles must not pay for or be distracted by evidence fields
they cannot return.

When a structured correction changes fields outside its closed write scope, runtime
must not discard a valid repair merely because the provider also rewrote unrelated
content. It may perform one call-free, role-neutral projection: start from the
immediately preceding invalid object and copy only values at the exact authorized
validation paths from the correction. Projection is eligible only when every path is
syntactically unambiguous and present in the correction; ambiguous list deletion or
shape change remains fail-closed. Runtime then reruns the unchanged role parser and
all semantic validators over the projected object. A valid projection is accepted and
emits `structured_correction_projection_applied` with the copied and discarded paths;
an invalid projection becomes the safe input to the remaining bounded correction, so
unrelated drift cannot be laundered through a later attempt. If projection is not
mechanically possible, the original strict scope failure remains in force and any
remaining correction repeats the original failed object and authorized paths. The
projection never invents content, relaxes validation, or adds a model call.
An issue that permits switching between mutually exclusive top-level outcomes must
name every contract-coupled discriminator and payload as an authorized dependency.
For H1, changing from `no_testable_hypothesis` to `hypotheses` necessarily permits
the linked `conclusion` and `no_hypothesis` changes; otherwise a valid correction
would be rejected as unrelated drift and an identical cached request could consume
the remaining recovery attempt.
For quantity failures, correction feedback additionally flattens every affected claim
and linked assertion into a counted literal checklist. Before return, each listed
missing literal must either be absent from every retained path or occur in a retained
`exact_text` attached to the identical final claim. Changing the string while retaining
the same unsupported literal does not satisfy the checklist. Each row includes
`missing_quantity_mentions` with the affected path, exact authored literal, half-open
character span, bounded verbatim context, normalized quantity group, and an explicit
complete-token boundary rule. Substring characters inside another numeric token do not
count as that occurrence. This makes a one-digit date/day, quarter, or amount as
executable as a long year or decimal without issuer-specific rules.

If both model corrections are exhausted, ResearchState roles have one deterministic,
call-free evidence-grounding phase. It is eligible only when every remaining obligation
names a complete Basic evidence row with an overlong, missing, non-contiguous, ambiguous,
or quantitatively unsupported literal, or names an unlinked quantitative assertion.
These migrated paths use stable `basic_literal_not_grounded`,
`claim_quantity_not_supported`, and `assertion_without_support` issue codes. Exact
invalid paths, permitted dependent assertion paths, candidate source refs, and numeric
repair details live in the typed issue fields; explanatory `message` text grants no
authority and changing its wording or punctuation cannot change recovery behavior.
Runtime removes only the named complete evidence items and byte-identical linked
beliefs/contradictions that no remaining identical evidence claim supports. It never
turns a raw filing/market literal into a belief, edits a claim, or remaps an ambiguous
literal to another projection. It refuses fallback if no evidence would remain.

Because an earlier validator may hide a later row-local grounding failure, runtime then
reruns the same parser and all local validators and may repeat the same mechanical
removal inside this single fallback phase. Every step must change the object, repeated
states stop the phase, and the step count is bounded by the rejected object's top-level
item count. Any lost required need transition, invalid decision, malformed shape,
identity leak, point-in-time defect, or other non-row-local residual error still rejects
the candidate. Cached provider responses remain unchanged and one
`structured_validation_fallback_applied` event records the role, exhausted correction
count, each fallback step, and the exact removed paths. Normal and successful-correction
paths pay no additional tokens, while one or two bad evidence rows no longer discard all
valid siblings in the case.
When partial Signal routing claims a facet retained by its residual, its correction
obligation additionally carries `remove_terms_from_selection_reason`. Shared topic
words are not themselves a contradiction. If the original target coordinates two
explicit normalized temporal values and the residual removes one side, runtime first
confines the conflict to the retained alternative value; this lets `2025 production
guidance` and residual `2026 production guidance` share their necessary topic while
rejecting a reason that claims both years. Without such an explicit split, the contradiction gate
prefers a shared ordered three-word phrase and also catches reordered overlap containing
at least three shared non-temporal content terms. Two shared non-temporal topic terms
plus a shared temporal term also qualify, so reordered period-qualified scope cannot
evade the same check. The selector must omit
every listed conflicting term from the named reason and describe only the narrower
answered facet, or remove the selection. These fields exist only in failed-call
feedback; runtime does not write the replacement and does not enlarge every normal
routing prompt.
An unchanged or near-complete residual is invalid input to that overlap inference.
A high token-overlap residual is nevertheless a genuine partial answer when it removes
at least one complete version-owned direct-answer phrase present in the target and
retains none of those phrases; a one-word measured facet is still a real facet. It is
near-complete when no such phrase was removed, or when it retains a version-owned
direct-answer phrase while removing at most one normalized content token. An explicit
coordinated-period split is also exempt because its one removed temporal value is a
real facet. When no literal residual clause can be separated, correction names both
the scope and residual paths and must choose full only if the card covers the complete
target, otherwise use a contextual reason or remove the selection.
For such a cosmetic residual, runtime first looks for an unambiguous top-level target
split: exactly one coordinated clause contains a version-owned direct-answer phrase
and at least one other clause remains. Correction receives those other literal clauses
as `residual_facet_candidates`, and only overlap with those clauses can produce
`remove_terms_from_selection_reason`. This prevents the diagnostic from labeling the
answered clause itself as residual. The candidates are bounded literal target slices,
not locally authored replacement prose; an ambiguous split yields no reason-scope
diagnosis until the model supplies a genuine residual. Possessive `s` is ignored as
punctuation residue. Structural exact-key errors likewise project missing and
unexpected keys to their leaf paths, keeping multiple correction obligations exact
and independent instead of asking the model to replace an otherwise valid object.
Residual/reason overlap ignores request scaffolding such as `directly covers`,
`reported/disclosed`, `figures`, and `fiscal`, just as it already ignores function
words. Shared issuer/date/source framing is not an answered facet; only a substantive
shared topic can make the selection reason contradict the residual.
When an exact version-owned need phrase rejects an empty routing result, the same
unambiguous split is attached to that failed call's `required_matches` target row as
`answer_scope=partial` plus `residual_facet_candidates`. This uses no extra model call
and leaves reason wording, tags, role, applicability, and the final natural-language
residual to the selector. Without a unique clause split, feedback does not guess the
scope.
The automatic ref-derived mandatory phrase is only the complete normalized Signal id
when it contains at least three words. Runtime never derives shorter n-grams from that
id: mentioning `operating cash flow` does not force an
`operating_cash_flow_margin` selection. Signal-owned synonyms or shorter direct
requests must be declared explicitly in version parameters.
An aggregate ResearchState item-count overflow is a combination constraint rather than
a claim that every contributing field is independently invalid. Its obligation
therefore carries `current_total_items`, `maximum_total_items`,
`minimum_removed_items`, plus `must_reduce_any_of_paths`, and the error reports current
per-field counts. The correction explicitly sums every returned array and must produce
`corrected_total_items <= maximum_total_items`; removing one belief and its evidence
counts as two items. It removes at least the stated number of total items
from any listed combination while preserving the smallest material decision frontier;
the runtime does not choose which semantics to discard. A field that independently
exceeds its own ceiling still uses a real `invalid_field` path and must itself change.
If the failed object itself proves that some items are structurally redundant, the
same aggregate obligation may carry bounded `structurally_redundant_remove_paths`.
Runtime may name only byte-identical later duplicates within one array or an open
question byte-identical to a next information need; it does not infer topical or
economic redundancy. To make aggregate correction executable rather than ask the model
to guess across six arrays, the obligation also carries bounded
`required_compaction_remove_paths`. It fills the removal quota in this contract-owned
order: an independently invalid whole-item path that can satisfy both obligations,
then a byte-identical duplicate, then the last `resolved_questions` bookkeeping item.
The final tier is safe because its answer remains in active belief/evidence state and
resolved bookkeeping is not an unresolved decision frontier. Runtime never selects an
economic belief, hypothesis, contradiction, evidence item, open uncertainty, or next
need by semantic opinion. The model removes every listed item, chooses any still-needed
remainder itself, and the normal count plus semantic validation reruns without local
output mutation.
`required_compaction_remove_paths` takes precedence over the alternative-array
instruction. The correction removes every exact path first; only if those paths do not
fill `minimum_removed_items` may it choose the remainder from
`must_reduce_any_of_paths`. When exact paths fill the quota and every other validation
obligation is either already within those paths, an explicitly open whole-array path,
or a byte ceiling that the removals alone satisfy, runtime byte-compares the raw
correction and rejects changes to unlisted content. If any remaining obligation has
unbounded legitimate linkage, or exact paths cannot fill the quota, validation stays
open and the normal parser determines validity. This enforces a closed scope only when
runtime can prove it complete without making runtime choose semantic content.

When a quantitative assertion fails only because it does not copy an evidence claim
byte-for-byte, correction feedback may add a bounded `copy_candidates_by_path` map.
For each invalid assertion path it ranks up to three exact claims already present in
the rejected output whose own evidence paths have no independently reported defect.
The correction may copy one exact candidate, remove the assertion, or first repair a
different evidence claim and then copy that final claim exactly. This is diagnostic
context only: runtime neither chooses a semantic replacement nor mutates the output,
and the unchanged parser and validators still decide acceptance after correction.
If one invalid numeric claim is shared by several evidence refs, the original defect
belongs to every same-claim `supporting_evidence[*].claim` path, not merely the first
ref used to report the missing quantity. One obligation therefore carries the missing
quantity groups, every same-claim evidence path, and every linked assertion path. All
such refs must share the same corrected claim or be removed. None may be offered as an
unchanged-valid copy candidate in that correction.
The same obligation carries the literal numeric substrings as authored in the claim,
in addition to normalized comparison groups. Correction can therefore delete the
actual unsupported text (or add a same-claim literal) without translating a scaled
value such as `4239700000` back into `$4,239,700,000`. If one endpoint of a comparison
is deleted, the claim must be narrowed to a grammatical single supported observation.

The evaluation-boundary reminder also forbids asking for the fixed baseline date
or baseline price: those are runtime-owned definition inputs, not issuer evidence.
This includes a scalar adjusted-close/share/stock-price lookup explicitly at the
prediction date or described as current/prediction-time price even when the model
does not use the word `baseline`; issuer-specific price/volume trend or market-
confirmation questions remain allowed. Raw H_init validation enforces this narrow
boundary on `open_questions` and `next_information_needs`, names the exact offending
path, and aggregates it with compaction/citation defects before the sole correction;
it does not attempt to answer or rewrite the question.
Every H_init/H_reflect `open_questions` and `next_information_needs` item must also
request evidence that could already be available by
`evaluation_context.prediction_time`. It may ask what the issuer had disclosed by then
about a scheduled future catalyst, milestone, or expected timeline, but it cannot ask
for later actuals, contents, results, announcements, approvals, partnerships,
milestones, or updates. Runtime rejects content-seeking dates after the cutoff,
reporting periods ending after it, ranges whose endpoint is after it, and unbounded
`after`/`since` windows without a cutoff-bounded as-of clause. Explicit as-of
disclosure/schedule questions remain valid even when they name the later event or
publication. Runtime supplies the same evaluation context to initialize and reflect,
names every exact invalid path in one correction, and never supplies the future fact.
This prevents a point-in-time-impossible retrieval and its otherwise inevitable
no-result routing call.
Cutoff-bounded questions about management commentary on demand, pricing, or operating
discipline use the same expectation boundary as guidance and outlook: they are valid
only when the wording asks what had already been disclosed by the cutoff and does not
request later results, actuals, or realized outcomes. A fiscal-period label inside such
commentary is not by itself evidence that the requested source contents are post-cutoff.
The same-state resolved/need consistency check treats a shared phrase as a topic only
when it contains semantic content. A phrase made entirely of period markers such as
`Q2 2025` is not enough to claim that a gold-price question was answered by a
production-cost question.
Its conservative two-word fallback also ignores a phrase that begins with the same
title-cased entity token in both questions, after removing possessive `s`; an issuer
name plus a generic metric such as `Kinross revenue` is context, not proof that both
questions ask the same unresolved facet. Any same-state resolved-question match must
also cover at least three quarters of the need's normalized content terms. Therefore
`production guidance` alone cannot collapse a compound Tasiast recovery-impact need,
and `construction progress` cannot collapse a remaining opening-timeline facet.
A three-or-more-word phrase is also ignored when every word is title-cased in both
questions: `Southern Illinois Connector` identifies the subject but does not answer a
separate capacity or market-share question. Visible Basic matching similarly abstains
when the need has an explicit residual-scope qualifier (`beyond`, `other`, or
`additional`) absent from the candidate; one known target does not answer a request
for other targets. The same qualifier abstention applies to a same-state resolved
question.
Generic subject tokens such as `company`, `issuer`, and their plurals are removed
before overlap matching, so the phrase `company revenue` cannot collapse a broad
recent-revenue answer into a still-unresolved quarter comparison plus EBITDA need.

The Predictor receives the compact ResearchState frontier and source index, not the
complete Basic projection text. H_init therefore keeps the smallest material direct
expectation evidence or counter-evidence visible in Basic Info—such as a price target,
management guidance, or issuer catalyst—when it bears on the fixed outcome. This does
not authorize an input summary or require one item per request; it prevents a market-
only frontier from making downstream analysis falsely claim that visible material
evidence was absent.

Fixed H_init and routing prompts state each runtime invariant once. Runtime-owned
eligible refs, executed-set filtering, selection caps, Signal versions, and enumerated
card constraints are supplied as data and validated locally rather than being requested
again from the model. Prompt compaction may merge repeated prose, but it must retain the
PIT/outcome boundary, literal evidence contract, valid empty-result rule, applicability
exclusions, direct-answer ownership, and exact output shape. Request preview, hash,
reservation, persisted request, and transmitted body continue to use the same compacted
bytes; lower prompt length alone is not evidence of higher research quality.

One evidence-kind diagnostic is one correction obligation. Its expected-kind clause
stays in the same segment as the exact `supporting_evidence[i].kind` path and must not
create an additional pathless row.
It also distinguishes the six-month repricing horizon from later operating events.
An event outside the horizon may matter through a point-in-time expectation change,
but H_init must not condition the six-month outcome on that later event already
having occurred; it instead names the evidence or milestone that could change
expectations inside the horizon.
Runtime supplies `evaluation_context` separately from Basic Info with the exact
prediction timestamp, fixed horizon kind, and horizon-end date. This control object is
not source evidence. For a conservative enforceable boundary, an H_init hypothesis
that combines an explicit event year later than the horizon-end year, an operating-
event term, and a 2x/share-price outcome is rejected unless it names a present
expectation or within-horizon transmission (for example progress, approval, financing,
bookings, guidance, forecast, a de-risking milestone, or explicit market
`priced in`/`pricing in` language). Current beliefs may still record the later event
date, and hypotheses may use it through a named expectation channel. The detector
must recognize this standard expectation-pricing construction rather than demand a
second synonym and reject already-correct reasoning.

For v6 Basic-Info evidence, the controller must copy one byte-for-byte contiguous
literal from one supplied projection: it may not use ellipses, join distant rows,
reorder JSON fields, or paraphrase `exact_text`. A literal that occurs exactly once
across the visible projection set is deterministically assigned to that projection;
otherwise correction feedback names the exact `supporting_evidence[index]`, supplied
projection, and matching projection ids before the candidate fails closed.
When an absent literal has substantial contiguous overlap with its named visible
projection, correction feedback also includes the rejected value, its occurrence
count, and at most one 800-character exact source window around that overlap. The
window is a bounded diagnostic from already supplied context, not an accepted
citation or local repair: the model must still author a replacement and runtime
revalidates the returned projection id and literal byte-for-byte against the complete
projection set.
Each Basic evidence claim must also be quantitatively supported by the literal refs
carrying that same claim: every numeric quantity in the claim must occur, after local
format normalization, in the union of those exact texts. Normalization includes exact
decimal scaling for an explicit adjacent thousand/million/billion/trillion word or
standard `k/m/mm/b/bn/t/tn` suffix, so `$1.6053 billion` is equivalent to raw
`1605300000`; it performs no rounding, tolerance, or inferred unit conversion. A claim spanning two market
endpoints may use two refs with the same claim; a lone beginning-balance literal cannot
support a beginning-to-ending decrease. Missing quantities receive one actionable
correction rather than being accepted merely because some literal exists. A year,
quarter number, date, or other temporal quantity present only in projection metadata,
a neighboring projection, or general document context does not support a claim; the
same-claim `exact_text` must contain it. Before the one correction, runtime aggregates
all locally decidable missing-quantity paths and every quantitative belief or
contradiction that does not copy an evidence claim, so correction is not asked to
discover a second independent defect after repairing the first. For an explicitly
listed missing quantity, feedback names deletion from the claim and linked assertion
as the minimal valid repair unless the role adds a same-claim literal containing it.
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
For a deterministic Signal, the compact result row instead exposes the exact canonical
numeric form once as `exact_claim_if_adopted`; the same value is not repeated in every
evidence row. A cited deterministic result copies that field byte-for-byte into its
evidence claim and any quantitative belief. Local validation treats that validated
derived record plus the cited source evidence as support. Rounded percentages,
converted units, and new raw quantities absent from both remain invalid.
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
its exact canonical `metric=value` interpretation once at result level as
`exact_claim_if_adopted`, while its evidence rows retain only index and timestamp;
the generic `interpretation` projection is omitted for that deterministic row so the
same claim is not supplied twice. H_reflect still cites the canonical local evidence
index. This is both clearer and smaller for results with multiple evidence spans.
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
The request additionally includes only each executed selection's `signal_ref`,
`reason_code`, `selection_reason`, and `target_need_indices`; routing-only
applicability, role, and context tags are omitted. A current direct answer also carries
its persisted `answer_scope=full|partial` and partial `residual_need`; non-answer and
legacy rows omit them. Runtime also derives one compact
`need_transition_contract.need_rules` row per prior need. Each row contains the exact
need plus its currently available direct-answer actions, unavailable direct-answer
refs, and contextual association refs. One routing round permits at most one direct
answer per target. If reflection adopts an available full answer, it removes that
exact target; if it adopts an available partial answer, it replaces the target with
the selector-authored exact residual. Retaining the old target, omitting the required
residual, substituting a cosmetic >=90%-topic-retention residual, supplying a residual
whose non-generic topic terms are mostly absent from the selected target, or removing
an unrelated need is rejected once, including in terminal reflection. A residual is a
narrowed derivative of its one target, never a different information need copied from
elsewhere in the same state. Other selection
reason codes and unavailable results require exact preservation. Runtime never chooses
the affected need itself. Old committed decisions without scope remain readable
through the legacy generic transition.
Selection may use
`answer_need` only when the card description directly covers at least one explicit
facet of the need. When a card exposes version-owned
`routing_answer_need_phrases`, one must already occur in the information-needs array;
accepted state or selector-authored reason/applicability prose cannot supply it. Its
reason names only that matched facet and does not promise that the Signal will answer
other facets. A merely contextual card uses `combine_evidence` or another accurate
reason code. Missing or invalid routing-only `context_tags` remains a shape defect but
does not short-circuit independently decidable target, residual, required-context, or
direct-answer checks on otherwise complete selection fields; the correction receives
all such defects together. Runtime does not insert a default tag into accepted output.
Correction feedback names
`invalid_field='next_information_needs'` and provides the prior indexed values; the
exact targeted field must change through an evidence-supported removal or narrowing,
but untargeted indexed items remain byte-for-byte.
Each transition error carries its own `required_action`: restore an untargeted prior
need exactly, replace an adopted partial answer with its exact residual, remove an
adopted full answer, or genuinely narrow a cosmetic target. Correction instructions
must not append one generic remove/narrow directive that contradicts a restore action.

H_init applies the same unresolved-only rule before any Signal call. It must not ask
again for a fact already present in Basic Info or in the evidence/beliefs it returns.
When a compound question is partly answered, `next_information_needs` contains only
the remaining facets. Most semantic scoping remains model-authored, but runtime
rejects the narrow cases it can decide without inventing an answer: (a) a need with
at least four normalized content concepts, at least 85% of them present in one
visible Basic Info projection, and a shared consecutive two-concept phrase; or (b) a
need sharing an ordered three-word content phrase with a `resolved_questions` item in
the same returned state, falling back to a non-titlecase two-word topic phrase only
when no three-word phrase remains. Possessive remnants and current/recent/latest
boilerplate are excluded, and a title-cased issuer-name bigram cannot satisfy this
gate. Case-common corpus terms are excluded from the first score,
and a small fixed normalization collapses inflection plus common upward/downward
revision wording. Feedback names the exact need path, matched projection or resolved
question, matched terms, score, and a bounded visible excerpt. Runtime neither
deletes nor narrows the item locally; lower-confidence and partly answered matches
remain for the model. These semantic issues are collected from the raw provider
object before compaction failure is raised, so one correction sees them together
with aggregate count/byte obligations rather than discovering them only after
compaction.

H_reflect uses the same stable correction transport as H_init and routing. Its initial
and correction system prompts are byte-identical and always describe the optional
`validation_feedback`. The initial payload ends with `validation_feedback=null`; the
correction changes only that field to the failed ResearchState and exact aggregated
error. It must not condition correction on a field absent from the actual payload.
This also keeps the ResearchState, Signal batch, selection intents, and runtime facts
as a provider-cacheable prefix instead of duplicating them under alternate top-level
correction keys.

H_reflect also receives a deterministic `research_state_capacity` map containing the
current/effective per-field counts, remaining new-item slots, combined-item capacity,
and canonical-byte capacity. This repeats no evidence and asks the model to select
within already enforced limits before it emits an oversized portfolio. A correction
that cannot pass the exact remaining-token preflight may still invoke the role's
existing call-free validation fallback over the already paid invalid response; the
fallback must pass the unchanged parser and scoped semantic validators. If it cannot,
the budget stop retains the paid usage and remains fail-closed.

The request also includes a runtime-owned terminal directive. It is true when the
current batch consumed the last permitted Signal round/call, when a soft-Signal
request was refused before transmission after deterministic results already
completed, or when completed batch usage reached the frozen terminal reserve.
H_reflect must then return a model-authored `finalize` state based solely
on visible accepted evidence; unresolved items may remain as needs/open questions.
An initial `continue` receives the single structured correction, while a repeated
`continue` fails closed. The runtime does not synthesize a terminal state, and the
actual boundary remains recorded separately as `termination_trigger`.
When all executed results are `unavailable`, H_reflect remains skipped because no
belief may change, except when a selected soft subgroup was refused after those
deterministic results completed or the completed batch reached the terminal reserve.
That exact terminal partial batch receives
`must_finalize=true`; H_reflect must preserve all research content byte-for-byte and
author only the `continue` to `finalize` decision transition. If the next ordinary
routing decision is empty or eligible cards are
exhausted, `no_signal_match` deterministically ends evidence collection: runtime
copies the complete last state, changes only `decision` to `finalize`, and preserves
every unresolved need/open question plus `termination_trigger=no_signal_match`.
This zero-call control transition cannot add, delete, restate, or reclassify research
content. Budget/round/call exhaustion without a reflectable terminal batch remains an
ineligible `continue` state rather than using this natural-exhaustion rule.
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
The 32,000-character projection is a ceiling, not a required payload size. Before
the first provider call, runtime uses the same exact provider-body byte reservation
as the external boundary to test the complete projection. When it cannot fit, the
runtime preserves one highest-ranked eligible projection per selected Signal when
that minimum fits, then greedily adds remaining ranked projections whose exact
payload still fits. The resulting request is the largest subset reached by that
stable pass; `context_contract` records `budget_trimmed=true` and the actual source
characters. If even the minimum cannot fit, the ordinary pre-send budget refusal
remains fail closed. A correction reuses the accepted initial projection unchanged;
runtime never discards evidence after seeing model output merely to make a repair
fit.
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
Raw-span mapping clips projection lineage to the returned quote's exact character
interval. One-to-one runs are sliced at the quote boundaries; collapsed whitespace,
decoded entities, and removed markup contribute only the intersected normalized
character's full raw run. Runtime then normalizes the mapped raw slice again and
requires a byte-exact round trip to the returned `exact_text`. It must never widen a
short quote to its complete projection window, because that would let unrelated words
elsewhere in the window satisfy a Signal's evidence-phrase contract or leak uncited
text into H_reflect.
For a quote touching an internal projection edge, validation feedback identifies the
supporting/counter index, rejected projection id, start/end edge, and overlapping
projection ids covering that source boundary. For each overlap, runtime may also expose
one bounded byte-exact complete-sentence candidate only when that sentence contains
the rejected normalized source boundary and touches neither internal edge. It never
selects the longest unrelated sentence elsewhere in the overlap. When no unique
boundary-anchored complete sentence exists, it exposes no candidate and leaves the
provider to choose another visible complete literal or return unavailable. This
makes the sole correction actionable while leaving the complete projections unchanged
and retaining model responsibility for choosing a candidate, another complete literal,
or unavailable.
For an absent, case-changed, punctuation-changed, or ambiguous quote, feedback likewise
identifies the evidence group/index, supplied projection id, occurrence count inside
that projection and across the Signal's eligible visible projections, and uniquely
matching projection ids. A generic “must map uniquely” error is not actionable.
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
the dynamic error, expected identity, returned refs, and required action are appended
only after the unchanged shared `source_projection` in the user payload. The rejected
row remains durable in the exact initial response and is not duplicated into the
correction request. A correction may use the smallest set of unique eligible literal
quotes required by the Signal skill, including current/prior or supporting/counter
pairs; it is never restricted to one quote when the versioned definition requires a
comparison. This preserves the complete Signal specs, skills, projection coverage,
and local validation boundary while making the large common request prefix eligible
for provider caching and keeping repair reservations below the case budget where the
unchanged evidence already fits. Pre-send token/cost reservation remains a cache miss,
and actual hit/miss usage remains durable evidence.

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

Routing tags remain non-semantic hints. Every non-empty selector item must return a
`context_tags` array, which may be empty and contains at most four values from the
supplied frozen vocabulary. The provider prompt includes that field inside the same
literal exact-field list as the other eight selection fields; it must not call the
field optional in a later clause. Runtime normalizes strings, deduplicates them, drops
values outside the vocabulary, and retains at most four in model order. A model copying
a visible card category such as `catalysts`, `risks`,
or `product` into `context_tags` therefore cannot reject an otherwise valid Signal
selection. A version-owned `routing_excluded_context_tags` list is the narrow
exception: if the selector attaches one of those tags to that same Signal, its own
applicability classification contradicts the visible card and receives the one
correction. Runtime never infers the tag or chooses a replacement Signal. Wrong refs,
missing fields, non-string tag containers, and invalid
reason/role enums retain their correction/fail-closed behavior.
`routing_required_research_phrases` is a second narrow version-owned gate: one exact
normalized phrase must already be present in supplied information needs or accepted
ResearchState context, never merely in the selector's new prose. `order_quality:v1`
uses customer-order/backlog phrases so an equity sale or financing transaction cannot
be relabeled as an order-quality problem by analogy. `commercialization_status:v1`
requires an existing product, technology, prototype, or commercialization phrase so
an established mining or operating project cannot be relabeled as a previously
non-commercial technical product merely by omitting `mature_operations`.

Before transmitting the selector request, runtime deterministically omits any card
whose required phrase is absent from the already accepted information needs and
ResearchState projection. It also omits a card whose version-owned exclusion
intersects a context tag accepted in an earlier routing round. These are monotone
applicability facts, so exposing such a card can only invite a known-invalid choice
and a useless correction. Current-output tags are still model-authored and therefore
remain subject to the post-output validator; runtime never infers a tag or picks a
replacement Signal. Exact-empty-match enforcement is computed only over the cards
actually supplied to the model.

The one routing correction receives one aggregated diagnostic pass. For every
structurally usable returned item, runtime reports target-index shape/bounds and
reason/role defects and every independently visible version-owned exclusion,
required-context, and
direct-answer-phrase defect together, naming the selection index and ref. A model must
not spend the correction fixing one invalid index only to discover that the same
selection was already an unsupported cross-domain analogy. A valid target on a
non-answer reason is retained as association metadata and causes no correction; only
`answer_need` target evidence can authorize a need transition. Items that cannot
be safely parsed remain rejected and are omitted only from further diagnostics, never
from validation itself; runtime does not repair or execute them.
When a row-level answer-scope or residual/reason contradiction is reported, the same
obligation explicitly permits changing that whole selection to a contextual reason
with null answer scope/residual, or removing it. This exposes a conservative correction
without asking the provider to invent an answered-facet paraphrase. After the frozen
correction budget is exhausted, a typed `routing_answer_ownership_invalid` failure
may conservatively retain the exact model-selected Signal as contextual evidence.
Only implicated answer rows change: clear answer scope/residual, use
`assess_applicability`/`coverage`, and replace the failed answer rationale with a
runtime explanation that ownership was unvalidated. Preserve the ref, association
index, context tags, and all sibling rows. This cannot resolve or narrow a need,
choose another Signal, or bypass applicability/evidence checks; rerun the complete
parser and record exact `context_only_paths`. No diagnostic wording is interpreted.
Other failures retain the call-free portfolio-row quarantine: it is
eligible only when every remaining obligation names one or more
`selections[index]` rows or descendants. Runtime removes the complete implicated rows,
preserves all other rows byte-for-byte and in order, then reruns the unchanged parser,
including unique-ref, capacity, direct-answer, applicability, and mandatory-nonempty
checks. If removal would violate a mandatory match or expose any other defect, the
candidate still fails. A successful fallback emits
`structured_validation_fallback_applied` with the exact removed paths. Quarantine
never edits a selection or chooses a replacement Signal; contextual fallback
executes only a revalidated row without answer ownership.
When an invalid empty selection contradicts a version-owned exact need phrase,
feedback names top-level `selections` plus each matching Signal ref, target need index,
and matched phrase. The correction therefore need not guess which of several needs
created the non-empty obligation. A partial answer starts from that exact target and
deletes its answered facet; it must never copy another supplied information-needs row
as the residual.
For every partial answer without an explicit coordinated-period split, runtime also
rejects a `selection_reason` that repeats a distinctive three-or-more-word phrase from
`residual_need`. Such a reason is claiming coverage of a facet the same row declares
unresolved. With an explicit split, only the retained alternative value is prohibited;
the common topic remains allowed. The correction names the exact
`selections[index].selection_reason` path and must describe only the answered facet;
runtime neither rewrites the reason nor deletes residual content.

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
usable evidence. If every completed deterministic result is unavailable, terminal
reflection is still required but may change only the decision; unavailable remains a
coverage diagnostic. A model-authored valid `finalize` earns
`stop_reason=finalized`, while the actual boundary remains durable as
`termination_trigger=budget_exhausted`; a repeated `continue` stays ineligible.
An initial preflight failure performs no attempt/network action. If the initial soft
attempt completed but its correction preflight fails, runtime still counts that paid
usage, converts only the pending invalid rows to canonical `unavailable`, and retains
already accepted siblings for ordinary whole-batch reflection. It does not label the
whole subgroup budget-exhausted merely because the larger optional repair cannot fit;
the next ordinary runtime guard decides whether further adaptive work remains. In
both cases the selection remains auditable in the exact routing response and
request-ready event.

When two LLM Signals share one deduplicated source projection, each compact Signal
entry lists its own `eligible_projection_ids`, derived only from that Signal's
resolved Raw Info documents. The role may read the shared projection once but may
cite only ids in the matching list. Mapping and validation enforce the same scope,
and correction feedback points back to that stable list. This prevents one Signal
from citing a document contributed only by its batch peer and avoids a predictable
paid correction without duplicating source text.

Chunk relevance uses each Signal's version-owned retrieval query and evidence
phrases. Extraction instructions are not search terms. Under the same shared
budget, selection alternates between Signals and prefers unseen eligible documents
before repeated chunks, so a long filing or a peer Signal cannot monopolize the
view while a short relevant source is already present. Normalization, source
timestamps, exact-span mapping and citation eligibility remain mandatory.

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
printed output. Signal statistics and learning events are post-pointer derivatives:
after a committed Plan round, failure while writing either stops before Slow, and
resume reconstructs both idempotently from the committed Plan records without
recomputing Fast predictions or charging new model calls. The raw trajectory keeps
the complete routing decision while the learning ledger receives only its explicit
stable learning projection. Slow validation is written as an exact immutable artifact before
Registry mutation. The exact transition is idempotently completed, the final
Slow result records input/output version/hash, and only then may the cycle
pointer advance and make that output the next cycle's input. The continuous CLI
supervisor may start successive bounded cycles, but `Ctrl+C` stops at the
current durable boundary without changing the frozen run contract, attempt
ceiling, cost ceiling, dataset, or Locked Test posture. It may leave only a
recoverable in-progress Signal transition, never an untracked partial rollover.
For `slow_bootstrap`, the frozen Fast target is zero, the round pointer remains
unchanged throughout, and the same Slow-validation/result order governs cycle
completion. A `committed_fast` bootstrap must reconstruct and verify its
manifest-bound learning/meta derivatives before H1, so actual H1/H2/H3 and
Update contexts consume the source Fast evidence even though the target has no
Fast pointer.

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

### Lossless reflection boundaries

Post-hoc context preserves the complete final state, baseline and cited Signal
material; its display target is advisory and exact wire budgets remain hard.
A Controller residual that loses a prior need's explicit cutoff may be restored
to that original need only when its topic is a literal contiguous phrase of one
unambiguous prior cutoff-valid need (ignoring punctuation and `any`). This is
restoration of a runtime-owned input, not creation of a new date-qualified fact.
Realized-result requests and unmatched or ambiguous rewrites remain rejected.

### V12 correction and temporal classification repair

After model correction is exhausted, typed `research_need_transition_invalid`
issues may use the existing bounded local recovery phase. Only runtime-issued
exact prior needs, residuals, and removal targets authorize changes; explanatory
prose grants no authority. Recovery changes only `next_information_needs`, records
the substituted path, and reruns the complete parser and semantic validation.
Unknown or mixed unsupported issues remain rejected; recovery cannot create
evidence, predictions, fitness, or a completed round.

All Controller corrections preserve unrelated siblings under the ordinary write
scope, including need-transition errors. Exact compaction scope is an additional
rule for actual compaction obligations, not a bypass for other errors.
A future fiscal period label (for example, a quarter ending date) does not itself
request future realized facts. An explicitly cutoff-bounded question about
already-disclosed guidance for that period is allowed. Requests for later actuals,
results, updates, or a future disclosure date remain rejected under the existing
as-of boundary. No current or realized quantity is inferred from guidance.
