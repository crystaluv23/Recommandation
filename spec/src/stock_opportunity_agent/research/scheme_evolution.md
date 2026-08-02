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
```

The implementation reuses the existing Ralph source archive, information-plan
preparation, anonymous packet, identity preflight, OpenAI/OpenRouter-compatible
client, and exact response cache. It does not implement a second document or
packet pipeline.

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
```

`state.json` records run id, iteration, lifecycle status, Top-K ids, current
tasks, checkpoint time, fixed-spec hash, proposal status, and whether final-test
was accessed. JSON checkpoints use temporary files plus atomic replacement;
events are append-only.

Each stock extraction and prediction is written immediately. Resume converts
stale `running` tasks to `pending`, reloads frozen materialization, and reuses a
prediction only when the exact genome recipe, frozen signals, label-free input,
extraction, evaluator/model settings, fold contents, and fixed rules hash to the
same value. A KeyboardInterrupt writes `paused`; provider or validation errors
write the task error and a resumable `failed` state. The OpenRouter adapter also
reuses an exact packet/prompt/model/provider/temperature response cache and
never persists credentials.

## Intermediate Progress Output

The CLI supplies a progress reporter to the evolution engine so a long round is
inspectable without opening partial JSON artifacts. Before evaluation, it prints
one compact summary per proposed genome: id, parents, mutation operator, target
failure type, changed fields, expected benefit, and falsification test. Static
rejections print their reasons before any expensive call.

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

The resulting `external_disclosure_preflight.json` records the fixed
OpenRouter endpoint, downstream provider/model, temperature, no-fallback and
required-parameter routing, candidate summaries, request count, per-request
anonymous packet/input hashes, conservative maximum cost, and the local packet
preflight locations. It scans the data payload for identity-bearing source ids
and forbidden label/outcome fields including `realized_max_multiple`,
`true_class`, and `is_surge`; any finding fails closed. Exact request content is
kept only in this local audit artifact, without credentials or authorization
headers.

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
request, and a conservative cost estimate. Because OpenRouter bills the panel,
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

The index scans only direct child run directories, validates each
`evolution_history.json`, and stores the histories ordered by most recently
completed round. The HTML contains the rendering and run-selection logic,
defaults to the most recently updated run, and reloads the adjacent generated
data script whenever it is opened or refreshed. Browsers do not permit a
`file://` page to enumerate arbitrary sibling directories or fetch arbitrary
JSON automatically, so the loop refreshes this local index after initialization,
every completed round, and `status` or `dashboard`. This is not one HTML per
round: the root path remains fixed while its local data index changes.

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

The thin script supports:

```bash
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
Dashboard coverage additionally verifies idempotent round history, no
final-test metric ingestion, direct-file script loading without `fetch`, empty
and partial histories, legacy latest-round recovery, multi-run index ordering,
invalid-run isolation, and the stable root entry path.

Synthetic, mock, and heuristic results prove orchestration only. Only a frozen
anonymous plain-LLM run on a declared untouched-company final test can support
an effectiveness or Phase-1 exit claim.
