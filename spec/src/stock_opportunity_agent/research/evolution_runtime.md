# Evolution Runtime Control Plane

## Status

Started

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
- Raw Info inventory hash;
- stable Signal Registry version/hash;
- fixed `H_R/H_P/H_E/H_U` hash;
- role/model/provider/routing metadata;
- code revision and Python runtime;
- candidate/round/runtime limits;
- maximum external attempts and cumulative cost; and
- `locked_test_accessed=false` for ordinary evolution.

An existing contract path may be reused only if canonical content is exact.
API-key availability is a boolean preflight fact and the key value is never
stored.

## External Request Boundary

Every request is canonicalized and written under `requests/<hash>.json` before
network I/O. Role-specific validation enforces:

- Predictor calls contain neither identity aliases nor outcome fields;
- prediction-time controller, retrieval, and Signal calls contain no outcomes;
- post-hoc reflection is the only Predictor stage allowed to receive truth;
- judge registrations are no-web and retries stay at one; and
- the request cites the frozen run-contract hash.

An attempt is reserved in `attempts.json` before the call. Reservation fails if
the attempt count or cumulative conservative cost ceiling would be exceeded.
Completion/failure updates the same durable entry. Exact responses live under
`cache/responses/<request_hash>.json`; reuse requires the exact request hash and
does not consume another attempt.

Preflight and dry-run never perform network I/O. External mode additionally
requires an explicit acknowledgement equal to the frozen contract hash.

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

## Testing

Cover secret-free canonical contracts, exact replay/conflict rejection,
request hashing, predictor leakage scans, preview no-network behavior, exact
cache reuse, durable attempt/cost reservation, stale in-progress attempt
visibility, local artifact inventory, missing paths, and Locked Test sealing.
Full-market expansion tests additionally cover fixed-date labels, incomplete
issuer exclusion, CIK deduplication, deterministic weighted/diversity sampling,
issuer-disjoint stratified splits, hashed official-source identity decisions,
date-bound CIK replacement/exclusion, immutable replay, and zero external calls.
