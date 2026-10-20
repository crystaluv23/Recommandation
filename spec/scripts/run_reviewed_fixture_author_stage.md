# Reviewed fixture-author module stage

Owner: `scripts/run_reviewed_fixture_author_stage.py`.

This diagnostic tests only the native S5 tests-author module. It does not run
Discovery/Mining/controller/cycle, install seeds, publish a stable Signal, or prove
S5 as a whole. The accepted spec is the current seed revenue-growth spec with only
signal_id=`fixture_author_revenue_growth` and version=1; skill is null. Synthetic
2023/2024 USD annual Revenues are 120/150, filed 2025-02-15, publicly available
2025-02-16 UTC, cutoff 2025-03-01 UTC. Two supported document schemas are required:
legacy nested SEC `facts.us-gaap.Revenues.units.USD` and typed
`sec-company-facts-document-v1`. Each schema has two short canonical JSON fact-row literals with format-specific
val/value keys; rows are copied only into their corresponding schema. A separate
homogeneous fixture is required per schema. For this fixed synthetic sample,
each schema fixture uses one complete financial document containing both
corresponding fact rows; this input condition is public in candidate requirements,
not a general restriction on Signal fixture schemas. Form is 10-K. CIK may use any valid
integer or digit-string representation of synthetic issuer 1 (never bool/float).
Fact rows and schema descriptions are short,
verbatim cited evidence, never long truncated bodies. The model receives the
native module prompt, accepted spec, candidate, shared contract and argument
schema through `_materialize_tests_module`; no authored answer is supplied.

The only authorized destination is
`runs/diagnostics/reviewed_fixture_author_stage_20261021_v1`. Preparation freezes
accepted modules, candidate, evidence, private expectations, catalog and current
Python/spec code bindings. Preparation never dispatches. Resume calls the native
module using a minimal module-only engine harness, real SignalCandidateValidator,
and an isolated empty task-local Registry/candidate directory. Accepted original
tests are staged and loaded byte-semantically unchanged. Independent checks run
those loaded fixtures with the real deterministic executor, require each schema
to have a successful positive at measurement 0.25 with explicit matching valid
CIK, and require publication/cutoff and exact synthetic fact rows. Actual schema fact
array entries must canonically equal the supplied corresponding row literals.
Unrelated body fields or literal carriers never establish fact identity. The
real executor supporting evidence for the positive fixture and its isolated
document must select exactly those two supplied rows, not same-ratio alternatives. Each qualifying
document is also executed alone, so a working schema cannot mask another
schema; both executions must measure the 2024 duration. Equivalent canonical
SignalSpec serialization retains seed formula and thresholds. Private checks
never substitute a different fixture or expected answer. Additional
fixtures retain the original spec/function's expected-value semantics.

Exactly one `mining_candidate_materialize_tests` request, native output limit
4000, no correction/semantic retries. Request and total logical reservation
ceilings are both 131072 (serialized message UTF-8 bytes plus output reservation;
not actual host tokens/cost). LocalRoleExchange and StructuredRoleClient run with
allow_external=False and empty environment. Invalid first JSON is terminal,
including otherwise reparable truncation; original raw answer is retained.
Unanswered requests are pending, not failures. Stage/root/budget/input/code drift
is rejected before dispatch. Terminal success or failure is sealed with exact
artifact hashes and restores only, never reenters the model or validator.
Network, LabelStore reads/writes, persistent RawInfoStore construction/appends and seed installation are
forbidden. Only native in-memory RawInfoStore appends are allowed, and Registry
construction is restricted to the two fixed task-local isolated directories.
The StageContract transport interface retains its minimum correction field 1;
the stage permits zero correction requests through its exact role/output budget
and first-answer wrapper. There is no promotion or real Registry access. Offline scripted callers
in tests prove wiring only; fresh authoring requires the independently submitted
native inbox/outbox receipt and subsequent independent artifact review.
