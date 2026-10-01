# Shared Fast/Slow Stage Contracts

## Purpose and ownership

The research runtime shares one contract for dependency checks, disclosure,
response validation, incremental repair, and checkpoints. Domain schemas,
evidence judgments and promotion remain owned by their current modules. This
module supplies small deterministic boundary helpers, not another agent engine.
The user authorized the integrated design and implementation on 2026-10-01.

## Stage dependencies and boundaries

| Stage | Required input | Excluded input / preserved boundary |
| --- | --- | --- |
| Plan proposal | proposal context: prior, parents, bounded experience and constraints | Original company identities; experience never forwards into blind execution |
| Initialize | initial skill, Basic Info, runtime evaluation anchor | Outcome labels; runtime numbers are not model reconstructed |
| Signal retrieval | cards, needs, applicability context, selection caps | Full source text and outcome labels |
| Signal execution | Signal specs/skills, eligible source projections, as_of | Unselected sources and future facts |
| Reflect | prior state, current batch, need transitions, patch contract | Outcome labels; unchanged fields retained by runtime |
| Predictor | typed final context with baseline, evidence, state evolution and effective state | Outcome labels and retrospective memory |
| Posthoc | immutable prediction, compact source context, revealed truth | Technical/data gaps cannot become factor-effectiveness judgments |
| Critic / Round | runtime metrics/comparisons, compact trajectories/records, source briefs | No rewritten lower-level originals; source closure mandatory |
| Slow reflection | pending feedback units, research/measurement contracts | No consuming unprocessed or failed feedback |
| Slow source selection | role scope, bounded source directory and read budget | No filesystem paths or hidden source contents |
| Mining | runtime axis/labels, evidence manifest, capability catalog, tool results, budget | Hidden check labels, model-authored labels, incomplete tool receipts |
| Materialization | one candidate, cited evidence; accepted spec/skill for subsequent modules | No regeneration of accepted independent modules |
| Update | one target, induction observations, mutable-field contract, relevant method context | Holdout; definition/tests immutable under existing rules |

Known production calls validate the required top-level dependencies before
transmission. A contract violation is a runtime construction error, never an
LLM response error and never eligible for output correction. Unknown extension
stages remain explicitly unregistered in request audit metadata. Registered
prediction-time stages require `allow_outcomes=False`; retrospective stages
follow the existing role-specific identity and label checks.

## Disclosure

Working inputs are bounded views of complete immutable artifacts. A catalog
page carries total, included, omitted-before/after, cursor and next cursor.
Every excluded entry remains reachable with its stable source reference.
Unread, fetched-but-insufficient and unavailable are distinct. Whole entries
are selected; summaries/previews disclose clipping and cannot replace exact
quote evidence. Selection never uses labels at prediction time.

Mining retains all feedback locally but exposes a bounded page of whole brief
entries and a discoverable directory. `inspect_catalog(scope=memory)` browses
that directory; selecting supplied `item_refs` reads complete entries within
an explicit byte cap. Omitted entries are not treated as absent. Evidence
catalog requests return actual titled rows, counts and pagination in the next
model input, not merely the names of result fields. Raw spans appear once in
the current action result with provenance, not as a repeated stale second copy.

## Detection and no progress

The owning validator checks structure, exact source references, numeric/PIT
constraints, state transitions and complete merged output. A pass proves these
checks only, not economic truth. Runtime separately checks dependency closure,
source versions, tool results and remaining budgets. Heavy, light and browse
caps cannot become negative. Inadmissible-budget actions receive one bounded
chance to switch; repeated budget inadmissibility defers the unit. Accepted
light actions cannot enable an unbounded no-progress loop.

No keyword checker claims to establish semantic truth. Lexical temporal guards
must handle ordinary inflections and preserve the explicit future-data checks.
Unknown/content failures preserve raw artifacts and valid siblings; provider,
budget, cancellation and other control-plane failures propagate unchanged.

## Incremental mechanical repair

Run applicable deterministic transforms first, even when other error classes
remain. Revalidate after every composed transform; only a full original-parser
pass accepts the output. When unresolved issues remain, retain the transformed
candidate and recomputed issues as the correction base. Partial candidates are
not valid/committed state. Never use diagnostic prose as repair authority.

Exact need restores/residual substitutions come from typed runtime-issued
transition context. Conflict between retained unanswered need and newly resolved
question exposes both paths as alternatives. Mechanical transforms may only
remove the unsupported newly resolved entry when the owning validator explicitly
marks that unique restoration consequence; they cannot guess a different answer.
Run bounded fixed-point recovery with visited-state detection. LLM corrections
receive only unresolved permissions, related evidence and the latest baseline.
All full-state/PIT/ownership checks run after merging. Schema/parse repair cannot
invent facts, alter labels or bypass promotion.

## Save, resume and acceptance

Accepted units are input/version-bound; dependent units require revalidation if
an upstream dependency changes. Candidate, accepted and committed remain distinct.
Existing atomic Fast/Slow pointers own completion. Repair logs preserve before,
after and operation paths; raw responses remain immutable. The Predictor is
assembled by the runtime from typed stage artifacts, with superseded/removed
state dispositioned explicitly; full audit history is retained.

Small-scale acceptance uses the same local Registry snapshot through Fast and
Slow, real model adapters for every exercised stage, and source-derived labels.
`scripts/run_minimal_rounds.py` prepares an immutable diagnostic subset of the
approved development splits, preserving issuer separation and sealing Locked
Test. Selection precedes model calls, uses a fixed seed plus label-store and
point-in-time source availability, and records every exclusion. The production v8 minimum
of 16 fixed Anchor and 8 Random cases retains the existing strata and fitness gates;
two real proposed Plans exercise Critic and Round reflection. Independent
Discovery uses 16 independent issuers (8 controls, 4 2-3x, 2 3-10x,
2 10x+) so direction has both classes on dev/check and magnitude has four
issuer-disjoint dev and four check cases, satisfying the existing paired floor. This diagnostic subset is not a new
formal benchmark or a paired comparison with the v154 cohort. A copied
Registry avoids writes to historical evolution workspaces. Raw Info remains
the shared global oracle outside this workspace; only source references and
hashes are frozen locally.
A hashed, source-specific integrity review can mark an exact immutable price
document as issuer-identity-unproven. Before cohort freeze, cases requiring
that document are ineligible and the cited reason is preserved; no numeric
label-to-source rewrite or post-model replacement is permitted. This narrow
diagnostic safeguard does not claim to repair all historical ticker routing.
Source and label baselines must refer to the same five pre-prediction dates.
Provider adjustment/rounding differences are recorded as retrospective audit
metadata, never used to substitute label prices into blind context or to select
companies by numerical equality with future-adjusted label archives.
The entry point uses the production exact-request transport, external-attempt
ledger, runtime evaluators, role adapters and commit pointers. Frozen run and
input hashes are verified on resume. `--prepare-only` performs no external
calls; an explicitly authorized `--run` executes the bounded cycle.
It preserves the frozen denominator and reports technical/data failures apart
from research errors. At least two complete Plans are needed to exercise actual
Round reflection. A stage that legitimately skips needs an explicit reason;
synthetic/mock outputs cannot be presented as live content acceptance. Inspect
saved requests, exact quotes, tool results, state changes, reflections, candidate
fixtures, independently checked outcomes and commit pointers. F1 improvement is
reported separately from execution completion; never tune labels/cohorts to
manufacture a passing result.
