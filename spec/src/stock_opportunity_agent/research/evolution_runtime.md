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
