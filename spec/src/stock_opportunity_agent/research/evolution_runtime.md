# Evolution Runtime Control Plane

## Status

Ready - v3 fail-closed contract implemented

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
- stable Signal Registry version/hash;
- fixed `H_R/H_P/H_E/H_U` hash;
- role/model/provider/routing metadata;
- code revision and Python runtime;
- candidate/round/runtime limits;
- a mandatory Fast-loop evaluation contract containing 20 exact cases,
  `8/6/4/2` label counts, primary and secondary metrics, the per-company cap,
  deterministic rotation seed, fitness eligibility, and bounded proposal/
  correction counts;
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

Only `evolution-run-contract-v3` may execute. Older frozen contracts remain
readable for status/audit commands but run commands return
`legacy_contract_read_only`; no missing evaluation field receives an implicit
default. Before creating requests or execution artifacts, runtime verifies the
exact Git revision, Python runtime, dataset hash, stable enabled-Signal snapshot,
and oracle id. Evaluation snapshots are immutable recovery inputs under the run
workspace. Their existence does not prove round completion or advance
`state.json:last_completed_round`.

## External Request Boundary

Every request is canonicalized and written under `requests/<hash>.json` before
network I/O. Role-specific validation enforces:

- Predictor calls contain neither identity aliases nor outcome fields;
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
case-sensitively; internal lowercase company ids are not added as global
free-text aliases. This still catches an explicit `AN`/`LOW` ticker leak but
does not misclassify ordinary prose such as "an artifact" or "low liquidity".
The current case's identity fields and aliases are independently stripped and
masked before this defense-in-depth scan.

An attempt is reserved in `attempts.json` before the call. Reservation fails if
the attempt count or cumulative conservative cost ceiling would be exceeded.
Completion/failure updates the same durable entry. Exact responses live under
`cache/responses/<request_hash>.json`; reuse requires the exact request hash and
does not consume another attempt.

Temperature is part of the exact request hash. Only Information Plan proposal
calls sample (`1.0`); prediction, research, reflection, Signal execution, and
all other judge calls remain greedy (`0.0`). The runtime alters temperature
only, leaving nucleus sampling at its provider default.

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

The Signal-result adapter also enforces the canonical unavailable-state
invariant. If a provider returns `state.value=unavailable` with a looser
coverage value, the boundary conservatively narrows coverage to `unavailable`;
it never promotes an unavailable state to partial or sufficient evidence.

Preflight and dry-run never perform network I/O. LLM external mode additionally
requires an explicit acknowledgement equal to the frozen contract hash. Source
data is controlled independently; when disabled, a local resolver miss records
`external_not_authorized` and performs no network I/O.

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

## Supervision, Interrupt, and Resume

The runtime emits structured, secret-free progress events before and after
request, cache, Plan, case, scoring, round-commit, and Slow-loop boundaries.
The workspace appends those events to its debug trajectory before forwarding
them to an optional caller callback. An external request interrupted after its
attempt reservation remains visibly `in_progress`; it is not silently retried
or marked unused.

One cycle freezes its start round and configured Fast-round count in
`cycle_state.json`. Resume calculates remaining Fast work from the authoritative
`state.json:last_completed_round`, not from files or printed output. The Slow
result is written as an exact immutable artifact before the cycle pointer
advances. The continuous CLI supervisor may start successive bounded cycles,
but `Ctrl+C` stops at the current durable boundary without changing the frozen
run contract, attempt ceiling, cost ceiling, dataset, Signal snapshot, or
Locked Test posture.

When no candidate is fitness-eligible, the runtime persists a deterministic
round-rejection checkpoint and capability-gap aggregation, emits a paused
status, and leaves both authoritative pointers unchanged. Resuming the same
immutable contract returns the same pause without repeating external calls.

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
- require complete baseline and forward-price eligibility at every requested
  date, rather than silently producing different case counts per issuer;
- exclude a listing when any requested prediction date precedes its recorded
  IPO/listing date, because pre-listing prices may belong to a reused ticker or
  a different historical security identity;
- deduplicate issuers by CIK when available and otherwise use a stable symbol
  identity;
- classify issuers into `<1.5x`, `1.5-<2x`, `2-<3x`, `3-<10x`, and `10x+`
  maximum-multiple strata across the requested dates;
- select deterministically from explicit stratum weights while rotating across
  exchange, IPO-age, and point-in-time dollar-liquidity buckets;
- split by issuer and selection stratum so no issuer crosses Discovery,
  Evolution Validation, or Locked Test ownership; and
- record source hashes, exact prediction dates, available/selected strata,
  exclusions, selection weights, seed, and the known sampling-bias boundary.

This is a label-aware retrospective dataset-construction step. Outcome labels
may select a learnable benchmark, but they never enter Raw Info or prediction
requests. Because positive and near-threshold strata are deliberately enriched,
unweighted benchmark F1 is a controlled comparison metric, not an estimate of
live market prevalence or expected returns.

The command writes immutable proposal artifacts only. It performs no external
calls, does not approve the proposal, and does not expose Locked Test to an
ordinary evolution run. New filing/news/profile acquisition begins only from a
reviewed exact issuer manifest, never by indiscriminately fetching the full
listed universe. It also emits a label-free acquisition scope containing only
company/CIK/ticker identities and required as-of dates. Data backfill jobs may
consume that scope without learning outcome strata or split ownership.

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
exact Slow-result staging, local artifact inventory, missing paths, and Locked
Test sealing.
Full-market expansion tests additionally cover fixed-date labels, incomplete
issuer exclusion, CIK deduplication, deterministic weighted/diversity sampling,
issuer-disjoint stratified splits, hashed official-source identity decisions,
date-bound CIK replacement/exclusion, immutable replay, and zero external calls.
