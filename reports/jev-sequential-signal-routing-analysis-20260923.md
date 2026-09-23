# Jev sequential Signal-routing analysis

Date: 2026-09-23

## Decision

Sequential Jev routing is the best Jev Signal selector tested so far. It is more
similar to the historical LLM than either per-card Jev design, obeys the
portfolio caps by construction, and costs less than the historical LLM. It is
slower per routing round because every next-card decision waits for the prior
answer.

The result supports continued sequential Jev experiments and retaining its
probability distribution as reflection feedback. It does not yet support a
production selector cutover or treating probability/confidence as canonical
Signal performance.

## Experiment boundary

- Frozen panel: the same 80 V139 routing rounds and 992 eligible-card instances
  used by the context-parity probe.
- Manifest:
  `06a8a6ee900334341083622ba2547dc7c08108d70da08387c92341d507996db1`.
- Every round started from the literal historical LLM initial user payload.
- Each step presented every remaining eligible Signal plus `stop` in one Jev
  choice. The selected ref, probability, stop probability, runner-up margin,
  confidence, and full distribution were appended to the next step's state.
- Selected refs were removed from later options. Remaining LLM-executed Signals
  were removed after two had been selected. The path ended on Jev `stop`, no
  eligible card, or the total cap of four.
- Preparation and execution read no outcome label and called no chat LLM,
  Signal, or research role. Scoring opened the historical portfolios and
  already persisted Signal result states only after all steps were durable.

All 80 rounds completed. The probe made 273 logical Jev calls and 277 physical
attempts. Four attempts failed with retryable SSL EOF errors; their retries
succeeded. There were no schema failures, unknown refs, duplicate selections,
total-cap violations, or LLM-cap violations.

## Portfolio behavior

Historical LLM selection is the reference behavior in this table. Precision,
recall, and F1 therefore measure selector parity rather than Signal correctness.

| Measure | Broad per-card Jev | Strict per-card Jev | Sequential Jev |
|---|---:|---:|---:|
| Selected refs | 312 | 263 | 218 |
| Mean selection size | 3.900 | 3.288 | 2.725 |
| Empty rounds | 1 | 7 | 0 |
| Rounds at cap four | 77 | 56 | 24 |
| Exact ordered agreement | 1.25% | 1.25% | **5.00%** |
| Exact set agreement | 6.25% | 2.50% | **10.00%** |
| Mean Jaccard | 0.420 | 0.357 | **0.469** |
| Micro precision | 0.506 | 0.498 | **0.642** |
| Micro recall | **0.635** | 0.526 | 0.562 |
| Micro F1 | 0.563 | 0.512 | **0.600** |

Sequential Jev retained 140 of the LLM's 249 selected refs and added 78 refs the
LLM did not choose. It stopped explicitly in 55 rounds, reached the cap in 24,
and exhausted eligible options in one. The first and second sequential choices
overlapped the LLM 77.5% and 69.0% of the time; the third and fourth choices fell
to 41.9% and 45.8%.

The paired mean-Jaccard improvement over strict per-card Jev was 0.112 with a
20,000-resample bootstrap 95% interval [0.046, 0.180]. The improvement over
broad per-card Jev was 0.049 with interval [-0.018, 0.115]. Sequential routing
clearly repairs the strict per-card topology, while its advantage over the broad
high-recall design is promising but not established by this panel.

Exact-set agreement remains only 8/80 rounds. Jev behavior is closer to the LLM,
not interchangeable with it.

## Speed and cost

Historical LLM figures come from the persisted V139 request, response, and
trajectory events for these exact 80 rounds. They are measured actuals rather
than current price estimates.

| Measure | Historical LLM | Sequential Jev | Change |
|---|---:|---:|---:|
| Logical calls | 80 | 273 | 3.41x |
| Actual cost | $0.100763880 | $0.063148764 | **37.3% lower** |
| Conservative charged cost | $0.100763880 | $0.071148764 | **29.4% lower** |
| Mean call latency | 4.28s | 2.38s | **44.4% faster per call** |
| Mean routing-round latency | 4.28s | 8.12s | **89.6% slower per round** |
| p90 routing-round latency | 4.85s | 11.46s | **136.2% slower** |
| Recorded tokens | 319,718 | 1,542,259 | 4.82x |

Jev preserves a cost advantage because its input-token price is much lower and
its output is a small typed distribution. The sequential dependency consumes
that latency advantage: a round needs an average 3.41 serial decisions. Rounds
can run concurrently for throughput, but the next choice inside one round still
waits for the previous choice. The historical LLM rounds could also be run in
parallel, so parallelism alone is not evidence of a model speed advantage.

## Incremental value of probability and confidence

For the 218 selected refs, choice probability and confidence had modest value
for predicting whether the historical LLM also selected the ref:

| Diagnostic | LLM overlap | Jev-only selection | AUC for LLM overlap |
|---|---:|---:|---:|
| Mean choice probability | 0.444 | 0.381 | 0.629 |
| Mean confidence | 0.378 | 0.316 | 0.607 |
| Mean runner-up margin | 0.238 | 0.175 | — |

The value is concentrated in the first two slots. Choice-probability AUC for LLM
overlap was 0.625 and 0.653 in slots one and two, then 0.436 and 0.497 in slots
three and four. Confidence AUC was 0.600, 0.615, 0.370, and 0.455. Raw values
also fall mechanically as the sequence progresses: mean choice probability was
0.478 in slot one and 0.315 in slot four; mean confidence fell from 0.425 to
0.215. A raw value from different slots or candidate-pool sizes is therefore not
directly comparable.

### Relationship to recorded Signal results

Only LLM-selected Signals have historical execution results, so this is a
selected subset rather than a fair performance sample.

| Historical result | Count | Retained by sequential Jev | Retention |
|---|---:|---:|---:|
| positive | 79 | 47 | 59.5% |
| neutral | 77 | 49 | 63.6% |
| negative | 66 | 28 | 42.4% |
| unavailable | 27 | 16 | 59.3% |

Choice probability barely separated positive from all other result states
(AUC 0.513); confidence was also near chance (0.529). On positive versus negative
only, probability reached 0.582 and confidence 0.623, a weak exploratory signal.
Neither predicted execution availability: AUC was 0.456 for probability and
0.445 for confidence.

These values currently describe Jev's decisiveness and preference within one
candidate pool. They do not measure whether a Signal produces available data,
positive evidence, a better prediction, or a better realized outcome.

## Metric design

Probability and confidence have incremental value when stored as routing
diagnostics with their context:

- chosen-option probability;
- probability of `stop`;
- margin over the runner-up;
- Jev confidence;
- slot number and number of remaining candidates;
- candidate-pool hash and previously selected refs;
- disagreement with the LLM or production selector.

Useful aggregate experimental metrics include slot-stratified selection rate,
median odds against `stop`, first-two-slot selection rate, runner-up margin, and
stability under repeated calls or candidate-order permutations. They can guide
reflection by identifying a decisive endorsement, a decisive veto, or an
unstable close choice.

Canonical Signal performance needs downstream evidence. The acceptance metric
should come from paired execution of the same cases with and without the Signal,
including availability, evidence coverage, prediction log-loss/F1 or magnitude
change, latency, cost, and held-out outcome contribution. Only a paired delta or
ablation can distinguish Signal quality from the contexts in which the selector
chose it.

## Recommended next use

Keep Sequential Jev as a shadow selector and feed its full distribution,
confidence, stop probability, and selector disagreement into reflection. Do not
add raw probability or confidence to Signal fitness yet. The next decisive test
is a frozen paired execution of LLM-selected and sequential-Jev-selected Signal
sets, followed by held-out comparison of downstream evidence and prediction
quality.

The production selector, Signal statistics, fitness, and promotion rules remain
unchanged.
