# Evolution Runtime Control Plane

## Status

Ready - v5 Anchor/Random cumulative Signal-transition contract implemented

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

Only `evolution-run-contract-v5` may execute. Older frozen contracts remain
readable for status/audit commands but run commands return
`legacy_contract_read_only`; no missing evaluation field receives an implicit
default. Before the first cycle creates requests or execution artifacts,
runtime verifies the exact Git revision, Python runtime, dataset hash, initial
enabled-Signal snapshot, and oracle id. On later cycles it verifies the current
stable snapshot against the last committed cycle output, not against the
initial contract snapshot. Evaluation snapshots are immutable recovery inputs
under the run workspace. Their existence does not prove round completion or
advance `state.json:last_completed_round`.
For v5, both model roles, code/runtime identities, and every consumed limit are
mandatory and type/range validated when the contract is loaded. Execution uses
those exact fields and never substitutes Python-side defaults.
Freeze additionally rejects an empty stable Signal Registry. The clean-worktree
check is scoped to runtime-bearing tracked paths (`src/`, `scripts/`, and
`configs/`) plus untracked files under those paths; unrelated progress or memory
notes do not make the executable HEAD unreproducible.

## External Request Boundary

Every request is canonicalized and written under `requests/<hash>.json` before
network I/O. Role-specific validation enforces:

- Predictor calls contain neither the current target's identity aliases nor
  outcome fields;
- prediction-time controller, retrieval, and Signal calls contain no outcomes;
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
artifact" or "low liquidity".

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

A provider response that is not exactly one JSON object is a paid structured
output failure, not a process-level crash. The runtime persists its raw model
text and usage in a failure-only audit artifact, records the actual cost on the
attempt ledger, and does not add it to the valid-response cache. Role adapters
then treat the malformed text as invalid output under their already frozen
single structured-correction allowance. If the correction also fails, the
existing candidate/role failure semantics apply; no parser exception may abort
the whole round or advance a commit pointer.

Temperature is part of the exact request hash. Information Plan proposal calls
sample at `1.0`. A dedicated Blind Predictor score call also uses `1.0`, solely
so provider log probabilities retain the model distribution instead of
collapsing to a greedy `0/-9999` shape; the runtime never adopts that call's
sampled token. Prediction explanation, research, reflection, Signal execution,
and all other judge calls remain greedy (`0.0`). The runtime alters temperature
only, leaving nucleus sampling at its provider default.

The dedicated score request does not repeat the complete Raw Info bundle. It
receives a deterministic label-free view containing the final research state
and Signal id/version/state/interpretation/status plus evidence counts and the
evolvable analysis prompt. Raw document spans and the Basic Info bundle are
excluded. Fixed six-month semantics override conflicting Plan text, while
retaining `H_analyse` here ensures that it still affects fitness. This keeps the frozen per-case token ceiling at `120000` without
introducing another summarization model or changing the original full-context
greedy explanation call.

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
not required. The provider-facing score output is a fixed single-token
contract: exactly the uppercase ASCII token `YES` or `NO`, with no whitespace,
punctuation, explanation, Markdown, or alternative casing. `YES` means the
model estimates at least 50% probability that the exact price outcome occurs
inside the horizon, and `NO` means below 50%. When usable log probabilities are
present, the adapter deterministically maps the pairwise `YES` probability at
the 50% boundary to `BlindPrediction.is_surge`; it never uses the
temperature-1 sampled token as the decision. A separate temperature-0
structured call receives that framework decision as immutable input and
returns the matching decision, qualitative confidence, reasons, uncertainties,
and magnitude. Positive decisions require a magnitude class, while negative
decisions require null magnitude. If token scores are unavailable, the score
call is skipped or discarded and the ordinary temperature-0 structured call
supplies the binary decision. The prompt also discloses that the evaluation set is
outcome-stratified and not representative of the live-market base rate, but it
does not disclose exact cohort counts, require a positive quota, or couple
separate predictions. This threshold and schema are fixed framework semantics,
not evolvable Plan content or case-outcome disclosure.

For the dedicated Predictor score call only, the exact request may ask a
provider that explicitly supports token log probabilities for up to 20
alternatives at the canonical single-token output position. The runtime prefers
the exact uppercase ASCII alternatives, never lets whitespace/case variants
overwrite a canonical alternative, and rejects provider sentinel values as
unavailable. It records
`yes_token_probability = exp(logp_yes)`, `no_token_probability =
exp(logp_no)`, and `decision_margin = sigmoid(logp_yes - logp_no)`. Provider
metadata is never accepted from the model-authored JSON itself. All three
values are optional and nullable together: a
provider without declared support, missing logprob payload, absent canonical
alternative token, sentinel value, or unparseable tokenization yields no
numeric values while the valid binary prediction continues normally. These
values are persisted in the blind
prediction and trajectory and are included in post-hoc and Plan-critic inputs.
After label reveal, feedback deterministically chooses `P(YES)` for a true YES
case or `P(NO)` for a true NO case as `truth_label_token_probability`, and
similarly maps the pairwise value to `truth_aligned_confidence =
decision_margin` for true YES or `1 - decision_margin` for true NO. Both
feedback values therefore improve toward one for either class. Fixed critic
prompts must explicitly use available values as calibration feedback, but
Binary F1 remains the only Plan-selection fitness and none of these values may
affect Top-K.

After truth reveal, the framework computes `prediction_outcome.correct` from
the immutable saved prediction and deterministic truth, including magnitude for
a true positive case. The reflection role receives that fixed bit and may
explain calibration or Plan failures, but model-authored disagreement cannot
overwrite it.

Preflight and dry-run never perform network I/O. LLM external mode additionally
requires an explicit acknowledgement equal to the frozen contract hash. Source
data is controlled independently; when disabled, a local resolver miss records
`external_not_authorized` and performs no network I/O.
An enabled data policy requires explicit non-empty provider, capability, and
source-type allowlists plus positive per-cycle and whole-run ceilings. The
operator must enable it once in the frozen contract and again for a resume
invocation; a request to execute data calls outside the frozen policy fails
explicitly rather than being silently ignored.
A disabled data policy has empty allowlists and zero ceilings; partially filled
but disabled policy data is rejected instead of being retained as ambiguous
latent authorization.

Information Plan proposal output contains only `B`, `H_init`, `H_reflect`, and
`H_analyse`. Runtime owns deterministic Plan ids and the exact selected-parent
lineage; provider-supplied ids are ignored. One correction request may repair
malformed content. An unrepaired candidate is rejected as a bounded event
without committing a partial round.

Each candidate slot may make at most three independently hashed proposal
attempts. Every structured runtime role receives at most one correction with
the failed output and validation message. Unrepaired initialization/prediction
failures terminate that candidate; non-fitness reflections degrade to explicit
deterministic failure records. Exact transport responses remain in cache for
audit, but a transport-cache hit is never treated as domain validation.

Model outputs are type-strict at the role boundary. JSON booleans, arrays,
objects, numbers, and required fields cannot be replaced by truthy strings,
character-wise iterable coercion, or implicit coverage/state defaults. A
malformed retrieval category/ref container receives the documented one
correction and then returns no match; it never terminates the process with a raw
container exception.

## Supervision, Interrupt, and Resume

The runtime emits structured, secret-free progress events before and after
request, cache, Plan, case, scoring, round-commit, and Slow-loop boundaries.
The workspace appends those events to its debug trajectory before forwarding
them to an optional caller callback. An external request interrupted after its
attempt reservation remains visibly `in_progress`; it is not silently retried
or marked unused.

One cycle freezes its start round, configured Fast-round count, and input Signal
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
