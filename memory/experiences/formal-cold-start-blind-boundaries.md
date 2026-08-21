# Formal Cold Start Blind-Boundary Drift

visit_times: 39

## Trigger

Read this before changing or running the formal cold-start workflow, especially
when the task mentions OpenRouter, GPT, blind LLM analysis, web search,
inflection discovery, anonymous stock packets, seed versus formal runs, or
single cold-start entry points.

## Lesson

The user's requirement was clear enough: the formal cold-start LLM assessment
step should receive an anonymous, point-in-time packet and judge whether the
stock looks like a potential surge case and what pre-surge signals are visible.
Implementation drift happened because the work was shaped around existing
scaffolding instead of restating and verifying the operational contract before
execution.

The main causes were:

- The formal run was treated as a composition of available code paths, so the
  old seed runner and the formal runner both remained visible and blurred the
  intended single entry point.
- Packet completeness was inferred from the existence of data-layer document
  abstractions, but the formal runner only wired price-derived features into
  actual packets. Support in a lower layer is not the same as operational use.
- Two LLM roles were not kept distinct enough: retrospective inflection
  discovery may use ticker identity, outcome windows, and web search; blind
  pre-surge assessment must use only anonymized as-of data and no web-search
  tool.
- Identity masking was checked at obvious fields such as ticker and company
  name, but not adversarially across packet ids, source ids, URLs, document
  text, and other metadata that can still reveal the company.
- The blind LLM schema asked for signal summaries, but did not explicitly ask
  for the core judgment the user expected: whether this anonymous case appears
  to be a surge candidate and why.

## Context

During the May 2026 formal cold-start work in `/Users/l/Project/Recommandation`,
the full-market scan and OpenRouter handoff exposed three issues:

- formal packets did not yet include filings, news, transcripts, or other
  unstructured material even though the architecture expects them;
- the blind prompt masked company fields but leaked the ticker through
  `packet_id`;
- the blind analysis step had no web-search tool, which was correct, but the
  separate retrospective inflection discovery step could use web search and
  needed to remain explicitly separate.

The gap was not caused by an unclear user request. It came from not pinning the
execution contract, acceptance checks, and role boundaries before adapting
existing code.

## 2026-05-09 Correction

The corrective implementation removed the redundant seed script entry point,
added a formal pre-packet context checkpoint for SEC filings, news, transcripts,
and news-derived catalysts, made point-in-time catalyst filtering explicit, and
tightened blind prompt masking across packet ids and text evidence. The lesson
to carry forward is that a clear architecture still needs an execution-contract
check at the boundary where old scaffolding is reused.

## 2026-05-13 Formal Execution Result

The clean formal run `cold-start-formal-openrouter-2026-05-13-clean-universe`
completed 300 blind analyses and wrote signal, theme, playbook, and manifest
artifacts. The run was operationally useful but not yet strong enough to seed
the long-running workflow without another improvement pass:

- OpenRouter JSON output can be malformed or truncated in both blind analysis
  and playbook synthesis, so completed blind analyses need checkpoint resume and
  late-stage playbook synthesis needs retry plus deterministic fallback.
- Filtering common stock before selection matters materially. The first
  universe pass admitted preferreds, notes, ETNs, funds, exchange test symbols,
  and same-issuer suffix variants; the clean rerun removed the obvious
  instrument pollution.
- Packet context remained too thin for signal learning. The completed run
  produced zero promoted deterministic signals, a single `unknown` theme map,
  and a playbook warning that most packets lacked fundamentals, sector,
  valuation, and catalyst substance.
- Blind LLM judgments did not separate winners from controls strongly enough:
  winner and control packets had nearly identical `possible` rates, while
  failure packets still produced many possible surge judgments. Treat this as a
  data/context and control-definition problem before moving into the permanent
  weekly/daily operating loop.

## 2026-05-16 Evidence Coverage Correction

The next correction was to add evidence acquisition before packet construction
instead of asking blind LLM analysis to compensate for thin packet context.
OpenRouter web search is allowed in this setup layer for public summaries,
theme context, and source URLs, but its outputs must become short
`DocumentRecord` summaries with publication/availability dates. Research-report
and theme-context documents are packet evidence kinds; full public reports or
article bodies should not be downloaded into durable artifacts.

The important boundary is the coverage gate: keep the full historical packet
audit, but do not treat every generated packet as learning-ready. In enforce
mode, packets without company evidence plus enough financial, theme, catalyst,
or risk context should be excluded before blind LLM calls and signal learning.

## 2026-05-20 Provider-First Evidence Smoke

The provider-only two-symbol smoke test showed that known APIs can materially
improve packet substance without crawler-like code. With Alpha Vantage
historical symbol news, SEC filings, provider profile context, and Finnhub/SEC
fallbacks, the context checkpoint reached dozens of documents and multiple
news-derived catalysts for the winner/control pair; the strict coverage gate
kept only the latest as-of slice for each side and excluded thinner earlier
slices.

Two operational lessons came out of the smoke:

- Free API quota is a research-quality constraint. Fetch company-specific news
  before broad theme/topic news so scarce calls are spent first on
  catalyst-bearing evidence.
- Provider error strings can include credentials. Adapter-level errors must be
  secret-redacted before warnings or artifacts are written.

The blind LLM distinction test could not complete because OpenRouter returned a
402 insufficient-credits response after packet/coverage construction. Treat
that as an external execution blocker, not evidence that the packet layer is
still empty.

## 2026-07-13 Information-Plan Boundary Correction

A full-source archive and a blind packet are different artifacts. Fetching a
filing and then storing only its 1,500-character packet excerpt destroys the
ability to distinguish acquisition failure from extraction or representation
failure. Preserve complete fetched filing/transcript bodies with an explicit
content scope, audit them before blind calls, and derive bounded packet views
later.

Anonymous masking must use identities discovered from the complete source pool,
not only the facts selected into one packet variant. Historical names,
acquisition targets, related organizations, and exchange-qualified ticker
aliases can survive otherwise-correct ticker/company masking. Reuse one
source-derived alias inventory across raw, organized, add-back, and ablation
packets, then scan every exact prompt variant.

Finally, a fixed raw context budget needs deterministic source coverage. If
chunks are appended document-by-document, one long recent 10-K can consume the
entire raw arm and turn a representation experiment into a file-order test.
Round-robin chunks across the frozen source pool before truncation. Keep this
mechanical and outcome-independent.

## 2026-08-02 External Disclosure Preflight

Permission to start a local research loop is not automatically permission to
transmit archive-derived packet text to a third party. Before an external blind
run, use the same request-construction path as execution to write a zero-network,
secret-free disclosure artifact containing exact request content, hashes,
routing, request count, and a conservative cost bound. Scan the data payload for
source case ids, identity aliases, outcome fields, and future values. A passing
artifact supports informed review but is never itself authorization.

For a truly bounded first run, freeze both analyzer retries and HTTP transport
retries to one. Otherwise a stated sample count does not equal the maximum
number of external requests and the apparent cost ceiling can hide retry risk.

## 2026-08-02 Fusion Role Separation

OpenRouter Fusion is not a stronger drop-in blind classifier: its panel and
analyst receive `web_search` and `web_fetch`, and one outer request expands into
multiple underlying completions. Keep it in the scheme-proposal and aggregate
reflection layer, where general source/method research is useful. Never pass it
validation packets or let its output directly produce TP/FP/TN/FN or Top-K.

Freeze blind scoring on a separate concrete model and provider endpoint that
supports the exact temperature, structured-output, reasoning, and no-fallback
parameters. Cache and locally validate the Fusion-produced full genome before
materialization so a drifting Quality panel cannot change an already-started
exam.

## 2026-08-02 Resume Attempt Budget

An external request limit must survive process failure. A per-process counter
is insufficient because a provider error can consume an HTTP attempt without
producing a cache entry, and a later resume would otherwise silently restore the
full allowance. Reserve each attempt in an atomic, secret-free ledger before
network access, finalize it as completed, provider-error, or validation-error,
and restore cumulative attempts plus observed cost in every new process.

Before resume, compare exact uncached preflight requests with remaining
authorized attempts. If the former is larger, fail before contacting the
provider. Extra attempts require a new CLI-only acknowledgement for the exact
increment; they must not loosen model, provider, no-fallback, packet, or cost
boundaries.

## 2026-08-02 Opaque Citation Contract

Provenance validation must follow the actual anonymous packet schema rather
than one remembered reference-key spelling. If packet items expose opaque
`fact_ref` values but the validator accepts only `fact_id` or `evidence_ref`, a
correct model citation is misclassified as hallucinated after a paid call.
Collect every explicitly supported opaque reference field from the supplied
packet, accept only literal values from that set, and keep rejecting cross-packet
or invented references.

Persist the raw provider output before parsing and provenance validation. An
append-only attempt ledger proves that a call happened, but response id, error,
and usage alone cannot reconstruct a stateless Responses API body after a local
validator defect.

Packet-visible lineage is part of the citation contract. If a derived item
exposes `derived_from_fact_refs`, those literal opaque values are visible to the
model and must be accepted just like the item's direct `fact_ref`; values not
present in either place remain invalid. Before spending another request on an
exact uncached input, revalidate any matching paid failed-validation audit under
the current local validator and promote it to the exact cache when it now
passes. Preserve the original validation error and cost in the audit trail.

## 2026-08-02 Prediction Versus Label Semantics

Do not compute partial TP/FP/TN/FN from `PredictionRecord.is_surge`. That field
is deterministically derived from the model's predicted A/B/C class; it is not
the hidden realized label. Confusion counts become valid only after the
label-free predictions for the evaluation unit are durably persisted and the
fixed evaluator joins them to `LabeledSample.true_class`.

Audit whether the prompt states the ordinal class mapping explicitly. A model
can write a clearly negative explanation yet output `C` if it assumes ordinary
alphabetic grading semantics, while this project's fixed contract defines `C`
as the strongest positive class. Treat explanation/class disagreement as a
prompt-contract failure for a future matched round; never remap the completed
class after labels are revealed. Hash the complete rendered developer prompt,
including immutable harness instructions, into the response-cache identity;
hashing only the evolvable template can silently reuse responses after a fixed
class-mapping repair. The zero-network disclosure preflight should recompute
that effective hash from the exact developer message, verify every immutable
class-mapping sentence, and compare the serialized user message with the
audited input payload; prompt correctness should be a fail-closed runtime gate,
not an operator eyeball check. A readiness artifact may persist only a boolean
for key availability, never credentials, and should calculate retry headroom
from the largest per-request estimate so the recommended attempt cap remains
inside the configured worst-case cost boundary.

## 2026-08-16 Full-Market Alias Collision Correction

A paid v5 Information Plan round rejected every candidate before its first
prediction because a full-dataset alias scan treated legitimate third-party
news text such as `UBS` and `S&P` as target-identity leakage. At the same time,
the target's composite SEC name did not cover natural references such as
`Kinross Gold` or `Kinross`.

Predictor anonymity is case-local: expand and mask the current target's id,
ticker, formal-name components, legal-suffix-stripped name, and distinctive
brand shorthand, then scan that assembled context again before transmission.
Do not scan every unrelated issuer alias in a full-market dataset. That rejects
valid evidence without adding protection against disclosure of the current
target.

## 2026-08-16 Prediction-Unit Ambiguity Correction

A paid v5 run completed a full 24-case Plan but predicted every case negative.
The fixed prompt asked whether the next six months would "reach at least 2x"
without naming the measured quantity. DeepSeek repeatedly treated that as a
requirement for revenue, earnings, production, or another operating measure to
double, while the frozen evaluator labels the target security's adjusted share
price using five-trading-day mean windows.

Blindness does not require hiding the label definition. State the exact
prediction unit, horizon, and smoothing rule in the fixed no-web prompt, and
state that operating measures are evidence about price repricing rather than
the target variable itself. This repairs prompt/label alignment without
revealing any case outcome or changing the evolvable Information Plan.

The immediately following canary showed a second semantic trap: even after the
unit was correct, the model rejected consecutive positive cases because the
evidence did not "guarantee" or explicitly forecast a doubling. A historical
blind classifier is a forecast under uncertainty, not a proof system. Define a
positive as a concrete, credible path to the price outcome, keep negative for no
credible path or dominant contrary evidence, and carry remaining doubt in the
existing confidence and uncertainty fields. Do not repair this by disclosing
class balance, forcing a positive quota, or changing completed predictions.

If the evaluator deliberately uses an outcome-stratified case-control sample,
the fixed classifier must also avoid importing the broad-market event rate as
its hidden prior. Otherwise a rare-event stock prior can dominate every case
and make an intentionally balanced F1 evaluation degenerate. Disclose only that
the sample is stratified and not prevalence-representative; do not disclose
exact class counts, force a class quota, share predictions across cases, or
pretend the resulting F1 estimates live-market precision.

Finally, keep the product decision boundary distinct from the hidden outcome
label. The realized label can remain an exact 2x adjusted-price event while the
blind opportunity classifier maps both `likely` and `possible` surge candidates
to its positive class. Requiring a greater-than-50% price forecast turns the LLM
into a price oracle, contradicts the product goal, and collapses rare-event
recall. Precision/recall/F1 against the exact future-price label is what
penalizes an overly broad or narrow candidate boundary.

When a model still applies a hidden greater-than-50% threshold to a direct
boolean, make the role output the explicit four-way judgment instead of adding
more prose beside the boolean. Deterministically map `likely` and `possible` to
the canonical positive record and `unlikely`/`insufficient_information` to
negative at the fixed adapter boundary. This preserves outcome labels and
metrics while making the intended opportunity threshold auditable.

## 2026-08-16 Human-Approved Binary Calibration Change

The user later explicitly replaced that opportunity-screening boundary with a
fixed binary decision: `YES` means an estimated probability of at least 50% for
the exact adjusted-share-price outcome, and `NO` means below 50%. This
human-approved framework change supersedes the four-way recommendation above
for the active Information Plan evolution runtime. Provider token probabilities
are optional reflection evidence only; missing logprobs cannot block a valid
binary prediction, and Binary F1 remains the only Plan-selection fitness.

The first corrected 48-case execution then showed why the prediction and score
boundaries must remain separate: both independent Plans authored `NO` for every
case under the literal 50% event-probability rule, including all 28 realized
positive observations. That is a real decision-policy outcome, not permission
to map the diagnostic score margin back into the prediction. Changing the
threshold or allowing a diagnostic bootstrap round is an explicit framework
choice and must not be hidden inside the probability adapter.

The same execution exposed a batch-reflection scaling trap. Serializing complete
24-case trajectories into the Plan critic repeated Raw Info and final contexts
until one request exceeded 1.2 million tokens. Plan-level feedback should use a
deterministic compact row with prediction, truth, token-confidence feedback,
post-hoc reflection, and Signal states/counts; omit identities, Raw Info, literal
spans, full research contexts, paths, and usage.

## 2026-08-16 Four-Way Opportunity Boundary Restored

The literal 50% binary decision produced `NO` for all 48 predictions across two
independent Plans on the same 24-case evaluation set. The user therefore
restored the last empirically non-degenerate interface: the provider returns
`likely`, `possible`, `unlikely`, or `insufficient_information`, and the fixed
adapter maps the first two to positive. The exact adjusted-price outcome label
and Binary F1 remain unchanged. The dedicated binary token-score call and its
probability/margin feedback are no longer part of the active Predictor.

Do not interpret this as evidence that two output strings inherently cause
collapse. The failure came from coupling `YES` to greater-than-50% probability
for a rare exact event and removing the explicit `possible` screening bucket.
Also audit the all-positive baseline on outcome-stratified batches: with 14
positives among 24 cases it scores approximately `0.7368` positive-class F1, so
a high F1 alone does not prove useful discrimination.

## 2026-08-16 Four-Way Feedback Must Survive Binary Projection

Mapping a provider's four-way opportunity judgment directly into a durable
boolean discards exactly the distinction needed for useful learning. Preserve
both the original judgment and its deterministic binary projection, reject any
mismatch, and let only the projection control Stage 2 and Binary F1.

After label reveal, derive feedback from the framework's fixed eight
judgment/truth combinations rather than asking an LLM to invent whether a call
was conservative, overconfident, or evidence-limited. Feed that record to both
case reflection and the compact Plan critic, but never add ordinal distance or
four-way penalties to fitness. One realized surge can make `possible` binary-
correct and conservative relative to the outcome; it cannot prove that
`likely` was the calibrated ex-ante probability category.

## How to Apply

Before executing or modifying formal cold start:

1. Identify the single official entry point and remove or clearly deprecate
   seed/demo paths from the formal execution surface.
2. Write down the phase contract:
   universe scan -> historical labels kept outside packets -> inflection
   anchoring -> T-180/T-120/T-90/T-60/T-30 as-of packets -> blind assessment.
3. Inventory actual packet contents from the runner, not just available data
   abstractions. If filings, news, transcripts, or catalysts are expected, prove
   they are loaded and passed into packet construction.
4. Audit the exact prompt JSON before spending LLM budget. Check labels,
   forward returns, ticker/company name, packet ids, source ids, source URLs,
   and document text.
5. Keep LLM role boundaries explicit: web-enabled retrospective inflection
   discovery is allowed; web-disabled anonymous blind surge assessment is
   required.
6. Treat coverage as a first-class gate: generated packets are audit material,
   while only context-sufficient packets should feed blind LLM learning when the
   formal run is in quality/enforce mode.
7. Add or run tests that assert no label leakage, no identity leakage, no
   web-search tool in blind analysis, and the expected blind output schema.

## Limits

This lesson applies to formal cold-start execution and historical blind case
learning. It does not forbid web search in retrospective setup or live research
stages when the spec explicitly allows those stages to use identity and web
retrieval.
