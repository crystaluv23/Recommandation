# Research / Information-Scheme Evolution

## Status

Started

## Purpose

Search for a better auditable information scheme while keeping the historical
exam fixed. The evolved object is `SchemeGenome`: the point-in-time data policy,
seed and discovery signal policy, and final analysis system prompt. Outcome
labels, A/B/C boundaries, splits, metrics, and model output fields are not
genome fields and cannot be changed by a candidate.

The layer remains retrospective, proposal-only, and separate from weekly or
live research defaults. A selected scheme still requires human review and a
fresh untouched-company test before it can support an effectiveness claim.

## Operating Spine

```text
freeze EvaluationContract and walk-forward split
-> import reviewed Codex/human candidate genomes
-> validate schema, leakage, cost, complexity, and recipe duplication
-> use signal-train labels to materialize and freeze signals per fold
-> build label-free anonymous validation inputs
-> persist each signal extraction and A/B/C prediction immediately
-> reveal validation labels only to the deterministic evaluator
-> rank old Top-K plus children by binary F1
-> behaviorally deduplicate equal binary prediction vectors
-> aggregate FP/FN/C-miss/ordinal diagnostics into structured meta-memory
-> checkpoint proposal-only Top-K and bounded next mutation requests
-> in continuous CLI mode, start the next bounded round after the checkpoint commits
```

The implementation reuses the existing Ralph source archive, information-plan
preparation, anonymous packet, identity preflight, OpenAI/OpenRouter-compatible
client, and exact response cache. It does not implement a second document or
packet pipeline.

## Execution Entrypoints and Model Roles

The controller is the single core flow for two entry paths:

- In a Codex conversation, Codex or a human writes a reviewed candidate file and
  the controller uses the `codex-reviewed-file` evolution registration.
- From the command line, the operator chooses one registered `evolution` model
  and one registered `judge` model. The evolution model may produce a complete
  candidate genome through the bounded proposal adapter; the judge model sees
  only anonymous point-in-time validation requests through the fixed blind
  adapter.

`models` is generated from the top-level LLM catalog on every process start.
The runner validates both aliases and their declared roles before initializing
a trajectory. It records aliases plus resolved provider/model/routing metadata
in `config.json`; a resume or inherited-round branch rejects a changed model
identity, while a fresh root trajectory may select another pair. Model
registrations may select one of the existing
standard proposal profiles (reviewed file, plain strict-JSON, or OpenRouter
Fusion) and must build a client conforming to the shared Responses-style
completion boundary. Adding another conforming provider or model therefore
changes only `stock_opportunity_agent/llm/`.

The proposal and judge roles never collapse into one mixed request. A web-
enabled evolution model may research general source or method ideas, but it
must not receive validation packets or per-company errors. A judge registration
must be no-web, fixed-route where routing exists, deterministic where supported,
and subject to the same disclosure preflight, attempt ledger, cache, label
isolation, and human-review rules as the current concrete adapters.

## Continuous CLI Supervisor

`launch` defaults to continuous mode: it repeatedly invokes the one-round
engine until the operator sends `SIGINT`/Ctrl+C or a fail-closed safety gate is
reached. “Continuous” is an outer scheduling policy, not one unbounded engine
transaction. Each round keeps finite candidate, retry, token, cost, and request
limits. A `--max-rounds N` compatibility/testing bound may stop cleanly after N
new completed rounds; omitting it means operator-stopped execution.
One advisory writer lock is held for the trajectory process lifetime, so a
second run/resume process cannot concurrently mutate the same checkpoints.

The supervisor advances only after the prior round has durably committed, in
this order:

```text
candidate response audit and parsed genome
-> per-sample extraction and prediction checkpoints
-> complete label-aware evaluation
-> Top-K and meta-memory
-> immutable round checkpoint and history
-> state status=completed for that round
-> next-round proposal context
```

Ctrl+C is handled at every point. If it arrives inside a provider call, the
external-attempt reservation remains consumed and the current task stays
`running` until the next launch atomically repairs it to `pending`; any received
raw response already written to the attempt audit is recoverable. Because an
interrupted HTTP request may have reached the provider without returning a
response, its reservation is never erased or treated as free; a later retry is
recorded as a separate attempt and remains subject to the cumulative cap. If
Ctrl+C arrives after all round artifacts commit, the round remains
`completed` and the supervisor writes `paused_by_operator` before exiting. The
next launch of the same trajectory first repairs stale `running` tasks to
`pending`, restores the last complete round checkpoint plus any exact per-task
artifacts from the interrupted round, and continues without regenerating
completed proposals or predictions. No resume path may delete a response audit,
reset cumulative spend/attempts, renumber a committed round, or treat a partial
round as complete.

Continuous external mode additionally requires a CLI-only session
acknowledgement and a positive cumulative session cost ceiling. The session
freezes evolution/judge aliases, resolved endpoints and routing, source corpus,
fixed spec, per-round candidate/request bounds, and retry policy. Every round
still constructs and locally validates the exact disclosure preflight before
transmission; a scope drift or cumulative-cost exhaustion pauses fail-closed.
The session authorization and cumulative ledger never imply final-test access
or production promotion.

## Fixed Evaluation Contract

`EvaluationContract` is serialized to `evaluation_contract.json` when a run is
initialized and verified by hash on every run or resume. Version 1 fixes:

- horizon: six calendar months;
- price field: adjusted close;
- continuous label: maximum complete five-trading-day moving-average future
  adjusted close divided by the prediction-date adjusted close;
- A: multiple below 2.0;
- B: multiple at least 2.0 and below 3.0;
- C: multiple at least 3.0;
- binary negative: A;
- binary positive: B or C;
- primary selection metric: binary F1; and
- diagnostics: binary precision/recall, multiclass macro-F1, per-class recall,
  class-C recall, and mean ordinal distance with A=0, B=1, C=2.

Every labeled sample stores `realized_max_multiple`, `true_class`, and the
derived `is_surge`. The fixed contract rejects changed boundaries, smoothing,
price fields, positive classes, or primary metrics. Legacy winner/control and
terminal-return artifacts cannot be silently presented as this contract; the
real runner requires a compatible adjusted-close history and derives new
labels.

## Evolvable Scheme

The existing richer records map to `S=(D,P,A)` without duplicating schemas:

- `DataSourceSpec` is the data policy, including retrieval, cutoff, freshness,
  expected cost, and failure behavior.
- `SignalSpec`, `contrastive_discovery_prompt`, and `signal_merge_prompt` are
  the signal policy. Signals define required sources, source cutoff,
  extraction, direction, horizon, contradiction/confounder handling, missing
  behavior, evidence schema, and version.
- `blind_analysis_prompt` is the final analysis system prompt.

Candidates record parents, mutation, changed fields, expected benefit, side
effects, falsification test, and target failure type. Each candidate should
make few attributable changes. `OpenRouterFusionSchemeProposer` is the optional
high-capability proposal adapter: it sends only the frozen objective, parent
genomes, sanitized aggregate meta-lessons, and mutation requests to the
web-enabled Fusion Quality panel. It never receives validation packets,
company ids, per-case examples, or final-test data. Its exact request and
current-price estimate are reviewed before one external call; the returned full
genome is cached, parsed, and passed through the same local `CandidateValidator`
before evaluation. `FileSchemeProposer` remains the frozen candidate handoff
used by the scored engine, and `MockSchemeProposer` remains the deterministic
test adapter.

## Signal Materialization and Blind Prediction

Discovery samples expose continuous and A/B/C labels only inside
`SchemeFoldEvaluator.materialize`. The resulting `MaterializedScheme` freezes
discovered, retained, and rejected signals with input/output hashes. Validation
receives only `BlindSample`; it contains no future price, realized multiple,
true class, binary label, ticker, or company name.

For each validation stock the evaluator produces and persists a label-free
signal extraction, then the analyzer returns:

- `predicted_class`: A, B, or C;
- `confidence_level`: low, medium, or high;
- `difficulty_level`: low, medium, or high;
- difficulty reasons;
- decisive signals;
- conflicting signals;
- missing information;
- flip conditions; and
- source evidence references required by this repository's provenance rules.

The immutable blind harness, outside the evolvable genome prompt, states the
class semantics verbatim on every request: A is a predicted smoothed maximum
adjusted-close multiple below 2.0 and is binary negative; B is at least 2.0 and
below 3.0; C is at least 3.0; B and C are binary positive. A negative thesis
must therefore map to A, never C. These definitions are target metadata, not a
validation label or realized outcome, and candidates cannot mutate them.

Opaque provenance references may use the packet's existing `evidence_ref`,
`source_id`, `fact_id`, or `fact_ref` keys, or a value explicitly exposed in a
`derived_from_fact_refs` lineage list. The validator accepts only values that
are literally present under one of those keys in the supplied packet and
rejects invented or cross-packet references.

`is_surge` is derived in code from the class. Numeric probability, likelihood,
logprob, score, future-price, or label fields are rejected. Confidence and
difficulty are qualitative diagnostics, not statistical probability and not
part of Top-K scoring.

The mock evaluator deterministically freezes seed signals and exercises the
whole flow without network access. The current Ralph adapter freezes seed
signals after source/coverage preparation and exposes its organized packet as
the extraction artifact. A provider-backed label-aware signal-discovery call
that can add, merge, or delete signals is still an explicit TODO; it must use
the same strict JSON, retry, cache, and label-boundary rules before it may
replace seed passthrough.

## Split and Isolation

- Signal-train samples may expose labels only to materialization.
- Validation inputs are label-free through signal extraction and analysis;
  labels are read only after prediction artifacts exist.
- Walk-forward construction requires the full six-calendar-month observation
  horizon plus purge and embargo to end before validation begins.
- One issuer cannot occur on both sides of a fold.
- Before fold construction, the real runner writes a label-aware dataset
  preflight that records every legacy case considered, the newly derived A/B/C
  class counts, and any deterministic exclusion. A case may be excluded only
  when its prediction-date adjusted close is absent or fewer than five future
  closes exist for the fixed smoothing window; the runner must not substitute
  an unadjusted close, old terminal-return label, or fabricated future value.
- Every selected fold must contain at least one binary negative (A) and one
  binary positive (B/C) in both signal-train and development validation. If
  class support is absent, the run fails before any blind provider call and the
  preflight remains the diagnostic artifact; a zero-positive F1 is not treated
  as an evolution result.
- Final-test records are absent from the engine constructor and ordinary run
  artifacts. The explicit command uses a separate one-shot path. The mock path
  is executable; real execution remains fail-closed until a separately
  configured A/B/C final-test dataset and source archive are supplied.
- Development validation can update structured meta-memory. Once used for a
  proposal, it is not independent evidence for that proposal.

## Evaluation, Top-K, and Memory

The evaluator saves binary confusion counts, A/B/C confusion counts, metrics,
continuous multiples, and sample-level errors. Reflection aggregation counts
repeated difficulty reasons, conflicts, missing information, confidence-level
accuracy, and difficulty-level error rates. Text length or apparent insight is
never scored.

Top-K merges prior retained schemes and the current batch, then sorts by:

1. binary F1 descending;
2. class-C recall descending;
3. ordinal distance ascending;
4. total API/data cost ascending.

Schemes whose paired binary prediction agreement meets the configured
threshold are behavior duplicates; only the better-ranked scheme remains. The
first implementation deliberately does not use MMR, DPP, MAP-Elites, or a
composite probability/calibration objective.

`MetaLesson` records observation, affected cases, diagnosed issue, tested
change, metric deltas, status, confidence, and supporting experiment ids.
Statuses are `hypothesis`, `validated`, and `rejected`. A child is marked
validated only when its measured target behavior improves and it is retained;
otherwise its reflection remains a hypothesis or rejected result.

## Persistence and Resume

Each run directory contains:

```text
config.json
evaluation_contract.json
state.json
events.jsonl
evolution_history.json
evolution_dashboard_data.js
evolution_dashboard.html
memory.json
schemes/
frozen_signals/
signal_extractions/
predictions/
evaluations/
prompts/
cache/
experiments/
rounds/round-<NNNN>/checkpoint.json
trajectory_lineage.json  # only for a branch
```

`state.json` records run id, iteration, lifecycle status, Top-K ids, current
tasks, checkpoint time, fixed-spec hash, proposal status, and whether final-test
was accessed. JSON checkpoints use temporary files plus atomic replacement;
events are append-only.

Every completed round also writes an immutable branch checkpoint containing the
round number, incumbent, complete Top-K archive, accumulated meta-lessons, next
mutation requests, and fixed-spec hash; model identities remain frozen in the
trajectory-level `config.json`. `resume` continues an
interrupted trajectory in place from its latest exact per-task state. Starting
from a completed historical round creates a new child trajectory instead: it
loads that round checkpoint, seeds the child archive/memory, copies only the
parent's public metric history through the selected round as `inherited_round`
rows, copies exact evaluation contexts only for genomes retained in that
checkpoint (their input hashes are revalidated before reuse), and records parent
trajectory plus parent round in
`trajectory_lineage.json`. It never truncates or overwrites the parent. A
pre-checkpoint legacy run may branch only from its exactly reconstructable
latest round; earlier non-reconstructable rounds are listed but fail closed.
The child config records its branch intent before seeding archive/history state,
so Ctrl+C during branch initialization can be recovered by resuming the child
trajectory instead of leaving an unusable directory.

Each stock extraction and prediction is written immediately. Resume converts
stale `running` tasks to `pending`, reloads frozen materialization, and reuses a
prediction only when the exact genome recipe, frozen signals, label-free input,
extraction, evaluator/model settings, fold contents, and fixed rules hash to the
same value. A KeyboardInterrupt writes `paused_by_operator`; provider or validation errors
write the task error and a resumable `failed` state. The OpenRouter adapter also
reuses an exact packet/prompt/model/provider/temperature response cache and
never persists credentials.

The prompt identity used by that cache is the hash of the complete rendered
developer prompt actually sent to the provider, including the immutable class
mapping and other harness constraints, not merely the genome template's stored
content hash. The exact input hash, effective prompt hash, and analyzer settings
all participate in the cache key. Any harness wording change must therefore
produce a cache miss and a new disclosure preflight.

Real blind runs additionally maintain `external_attempts.json` as an atomic,
secret-free HTTP-attempt ledger. The analyzer reserves one entry immediately
before each provider call, so a timeout, process interruption, provider error,
or invalid response still consumes one authorized attempt. Every completed
response records its observed or conservative estimated cost, and a new process
restores both cumulative attempts and cumulative cost before considering a
resume. Exhausting either the authorized attempt count or the configured cost
cap fails before network access. The ledger is scoped to the exact reviewed
preflight hash and analyzer settings; mismatches fail closed.

After a provider response arrives, its secret-free raw output, response hash,
usage, and cost are atomically written under the analyzer cache's `_attempts/`
audit tree before JSON or provenance validation. The audit record is finalized
as validated or failed-validation; a valid response cache also retains the raw
output. Provider failures without a response body remain represented by the
external-attempt ledger. A validator defect therefore cannot erase an otherwise
inspectable paid response. Before making a new request for an uncached exact
input, the analyzer revalidates matching failed-validation audits under the
current local contract. A newly valid audit is promoted to the exact cache
without another HTTP attempt or another charge; its original validation error
and paid cost remain auditable.

## Intermediate Progress Output

The CLI supplies a progress reporter to the evolution engine so a long round is
inspectable without opening partial JSON artifacts. Before evaluation, it prints
one compact summary per proposed genome: id, parents, mutation operator, target
failure type, changed fields, expected benefit, and falsification test. Static
rejections print their reasons before any expensive call.

At launch it first prints the selected trajectory action, trajectory id, source
round when branching, evolution model, judge model, provider routing, output
directory, and fixed development/proposal-only boundary. During evaluation it
prints a bounded per-sample line only after the prediction has been persisted,
including genome, fold, sample progress, cache/new status, predicted class, and
qualitative confidence. Hidden labels and partial confusion counts remain
absent until the complete persisted evaluation is available.

Before each new continuous round it also prints the round number, committed
checkpoint it is building from, completed/remaining session cost, cache
coverage, and the next mutation requests. On Ctrl+C it prints exactly which
round/task was paused and the one resume command; this message is derived from
the state just written, not from an in-memory guess.

After a genome's predictions have been persisted and its development labels are
revealed to the deterministic evaluator, the reporter prints its confusion
counts, binary F1, class-C recall, mean ordinal distance, and total data/token
cost. At the end of each round it prints every Top-K rank with the same fixed
metrics plus each candidate's retained/not-retained decision and binary-F1
delta. These lines are explicitly development, proposal-only diagnostics; they
must not include final-test metrics or imply an effectiveness claim.

Progress output is observational only. It must not change proposal sampling,
candidate validation, cache keys, ranking, admission, persistence order, or the
fixed evaluation contract. Label-aware scores may appear only after the
corresponding label-free predictions are durably written.

## External Disclosure Preflight

Real LLM mode has a separate zero-network `external-preflight` command. It
materializes the same baseline and statically accepted candidate genomes on the
same selected folds, then uses the analyzer's shared request-construction path
to persist the exact developer/user content and request parameters that a later
`run` command would send. The preflight must not call the provider, read
validation labels into request content, or mutate the evolution iteration.

The resulting `external_disclosure_preflight.json` records the registered judge
alias, exact endpoint, provider/model, temperature, no-fallback and required-
parameter routing when the provider exposes routing, candidate summaries,
request count, per-request
anonymous packet/input hashes, conservative maximum cost, and the local packet
preflight locations. It scans the data payload for identity-bearing source ids
and forbidden label/outcome fields including `realized_max_multiple`,
`true_class`, and `is_surge`; any finding fails closed. Exact request content is
kept only in this local audit artifact, without credentials or authorization
headers.

For every request the preflight also independently checks that the rendered
developer prompt contains all immutable A/B/C threshold and binary-polarity
sentences, that its SHA-256 equals the advertised effective prompt hash, and
that the serialized user message equals the audited input payload. These
contract findings share the same fail-closed gate as identity or label leakage;
the artifact records checked and passed request counts.

The same artifact includes a secret-free execution-readiness summary. It
records only whether the registered provider credential was available at
preflight time, whether
final-test remained sealed, how many exact responses already exist, and the
largest retry buffer whose worst-case per-request estimates still fit the
configured blind-cost cap. It names every technical blocker separately from the
always-required explicit transmission authorization; it never persists the key
or treats key presence as authorization.

The external run is still unauthorized by the existence or success of this
artifact. It requires explicit informed approval covering transmission of the
anonymous local-archive-derived text to both OpenRouter and the fixed downstream
provider. For the first bounded run, logical analyzer retries and HTTP transport
retries are both fixed to one so the preflight request count is also the hard
maximum external request count.

Fusion proposal generation has a distinct zero-network `fusion-preflight` and
an explicitly authorized `fusion-sample` command. The preflight freezes the
`openrouter/fusion` Quality preset, one web/tool step per panel or analyst,
inner/outer output bounds, resolved-alias pricing snapshot, exact scheme-only
request, and a pricing-snapshot cost estimate. Because OpenRouter bills the panel,
analyst, outer model, and web calls together, this estimate is recorded as a
snapshot estimate rather than misrepresented as a provider-enforced per-request
hard cap. The successful candidate response is cached and frozen to the run's
candidate JSON before any blind-data materialization.

The blind analyzer may separately freeze a concrete OpenRouter model endpoint,
reasoning effort, output-token bound, temperature, structured-output contract,
and no-fallback routing. The current Kimi configuration uses
`moonshotai/kimi-k3` through the exact `together` endpoint at temperature zero
and max reasoning; Fusion settings never enter the blind analyzer fingerprint
or request body.

External `fusion-sample` and real LLM `run`/`resume` require the CLI-only
`--external-transmission-authorized` acknowledgement; experiment JSON cannot
store it. Before a blind call, the runner hashes and revalidates the adjacent
passed disclosure artifact against the model, exact provider, temperature,
reasoning effort, output bound, no-fallback routing, request count, findings,
and cost cap. It writes a separate secret-free authorization record and event.
A stale flag therefore cannot authorize a request that differs from the exact
reviewed preflight.

A failed HTTP attempt is not erased by `resume`. When the original request
allowance has been partly consumed without producing a cached prediction, an
operator may extend it only with the CLI-only
`--authorized-extra-http-attempts N` acknowledgement after obtaining explicit
approval for that exact increment. The field is rejected in experiment JSON,
is valid only for `resume`, and is written to the refreshed authorization
record. It expands only the cumulative HTTP-attempt ceiling; model, provider,
packet set, no-fallback routing, and API cost cap remain frozen.

## Local Drift Dashboard

Every completed development round atomically upserts one entry in
`evolution_history.json`, keyed by the engine iteration. An entry contains the
completed timestamp, selected incumbent, retained archive-best metrics, and one
row for each evaluated child with its admission decision and fixed metrics.
The record contains development validation metrics only; final-test artifacts
remain under `final_test/` and are never imported into this history.

`evolution_dashboard.html` is a dependency-free local report. It loads the
adjacent `evolution_dashboard_data.js` with a normal script tag, so opening the
HTML directly through `file://` works without a local server, browser file
permissions, or network access. The data script is regenerated atomically from
the canonical JSON history after initialization, every completed round, and
the `status` or `dashboard` command. Existing runs with only the former
`scheme_experiments.json` and `top_k.json` receive one explicitly marked
recoverable legacy snapshot rather than fabricated missing rounds.

The standard evolution root additionally owns one stable entry point:

```text
runs/cold_start/evolution/evolution_dashboard.html
runs/cold_start/evolution/evolution_dashboard_data.js
runs/cold_start/evolution/evolution_dashboard_index.json
```

The index scans only direct child trajectory directories, validates each
`evolution_history.json`, and stores the histories ordered by most recently
completed round. Each trajectory row includes its evolution/judge model aliases
and optional parent-trajectory/round lineage. The HTML contains the rendering
and trajectory-selection logic, defaults to the most recently updated
trajectory, displays the chosen model pair and branch origin, and reloads the
adjacent generated data script whenever it is opened or refreshed. Browsers do not permit a
`file://` page to enumerate arbitrary sibling directories or fetch arbitrary
JSON automatically, so the loop refreshes this local index after initialization,
every completed round, and `status` or `dashboard`. This is not one HTML per
round: the root path remains fixed while its local data index changes.
If `status` sees an active writer lock, it remains read-only and skips dashboard
regeneration; the running supervisor refreshes the page at its next completed
round.

Per-run HTML remains as a compatibility and portable-run view. Both root and
per-run pages use the same executable HTML template; the per-run data bundle
contains one history, while the root bundle contains all valid local histories.

The default effect metric is the frozen primary metric, binary F1. The chart
uses round number on the horizontal axis and effect on the vertical axis, and
simultaneously renders:

- every accepted child score as a stochastic candidate point;
- the per-round candidate median as the drift-sensitive sequence; and
- the retained archive best as a separate best-so-far line.

The report must explain that the archive line is monotone by construction and
therefore cannot by itself demonstrate upward drift. It shows the ordinary
least-squares slope of the round medians only when at least three rounds are
available; this slope is descriptive and not an effectiveness or statistical
significance claim. Missing or partial history renders an empty/partial state
instead of failing the underlying evolution run.

## CLI

The thin script supports both explicit parameters and an interactive launcher:

```bash
PYTHONPATH=src python scripts/evolve_information_schemes.py models
PYTHONPATH=src python scripts/evolve_information_schemes.py trajectories
PYTHONPATH=src python scripts/evolve_information_schemes.py launch --trajectory-id <new-id> --trajectory-action new --evolution-model codex-reviewed-file --judge-model local-heuristic --config <config.json>
PYTHONPATH=src python scripts/evolve_information_schemes.py launch --trajectory-action resume --from-trajectory <existing-id> --config <config.json>
PYTHONPATH=src python scripts/evolve_information_schemes.py launch --trajectory-id <branch-id> --trajectory-action branch --from-trajectory <existing-id> --from-round <N> --config <config.json>
PYTHONPATH=src python scripts/evolve_information_schemes.py init --config configs/evolution/mock_experiment.json
PYTHONPATH=src python scripts/evolve_information_schemes.py run --config configs/evolution/mock_experiment.json
PYTHONPATH=src python scripts/evolve_information_schemes.py resume --config configs/evolution/mock_experiment.json
PYTHONPATH=src python scripts/evolve_information_schemes.py status --config configs/evolution/mock_experiment.json
PYTHONPATH=src python scripts/evolve_information_schemes.py dashboard --config configs/evolution/mock_experiment.json
PYTHONPATH=src python scripts/evolve_information_schemes.py fusion-preflight --config configs/evolution/real_kimi3_fusion_development_v1.json
PYTHONPATH=src python scripts/evolve_information_schemes.py fusion-sample --external-transmission-authorized --config configs/evolution/real_kimi3_fusion_development_v1.json
PYTHONPATH=src python scripts/evolve_information_schemes.py external-preflight --config configs/evolution/real_kimi3_fusion_development_v1.json
PYTHONPATH=src python scripts/evolve_information_schemes.py final-test --config <real-config.json>
```

When `launch` runs in a terminal without `--trajectory-action`, it lists the
same local trajectory catalog and prompts for new, resume-latest, or branch-
from-round. In non-interactive use those choices must be explicit. `models`
prints the auto-discovered aliases and role support; `trajectories` prints local
rounds, lifecycle status, model pair, branch lineage, and exactly branchable
rounds. `--evolution-model` and `--judge-model` are stable aliases, while old
provider-specific flags remain compatibility overrides and must match the
selected registration.

`launch` continues indefinitely by default. `--max-rounds` is intended for
tests, smoke runs, scheduled batches, or operators who explicitly prefer a
finite session. External continuous execution additionally requires
`--continuous-external-session-authorized` and `--session-max-cost-usd`; both
are CLI-only and cannot be smuggled through experiment JSON. Re-running the same
launch command resumes the current partial round first, then continues with new
rounds until interrupted.

The mock `final-test` command evaluates the selected proposal once on separate
sealed synthetic companies and writes only under `final_test/`. Real
`final-test` fails closed with a clear message rather than reading a development
label source. Real LLM execution additionally requires `OPENROUTER_API_KEY`, an
exact provider slug, positive current token-price inputs, disabled provider
fallback, explicit single-attempt retry bounds, and a compatible price-history
artifact. The zero-network external preflight deliberately does not require a
credential.

## Testing

Tests cover genome serialization, frozen contract mismatch, five-day smoothed
labels, A/B/C-to-binary mapping, fixed metrics, point-in-time and walk-forward
guards, atomic checkpoints, append-only events, interruption/resume without
duplicate calls, exact analyzer cache reuse, malformed JSON retry, probability
field rejection, label-free analyzer inputs, Top-K behavior deduplication, a
two-generation mock flow, final-test exclusion, and packet identity preflight.
Request-preview coverage additionally verifies that the shared preview path
performs no provider call and contains no source case id or validation label.
Dashboard and trajectory coverage additionally verifies immutable branch
checkpoints, exact archive/memory restore, parent preservation, inherited
history marking, idempotent round history, no
final-test metric ingestion, direct-file script loading without `fetch`, empty
and partial histories, legacy latest-round recovery, multi-run index ordering,
invalid-run isolation, registered model/lineage display, and the stable root
entry path. Catalog tests verify lazy module discovery, role validation, unique
aliases, and preview-only client construction without a credential or network
call.

Continuous-supervisor coverage interrupts between sample predictions and
reserves a simulated in-flight external request before restart. Together with a
real CLI Ctrl+C/resume smoke path, it verifies atomic JSON, append-only
attempts/events, pending-task repair, no duplicate completed calls, conservative
accounting for uncertain in-flight calls, monotone
committed round numbers, restored Top-K/meta-memory, cumulative-cost
restoration, and clean continuation into the interrupted round.

Synthetic, mock, and heuristic results prove orchestration only. Only a frozen
anonymous plain-LLM run on a declared untouched-company final test can support
an effectiveness or Phase-1 exit claim.
