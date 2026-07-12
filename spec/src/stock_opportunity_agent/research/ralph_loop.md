# Research Ralph Loop

## Status
Started

## Purpose

Improve the information scheme used for cold-start blind LLM assessment without
promoting prompt changes into the long-running daily or weekly workflow.
Ralph Loop v1 is a historical-learning/meta-learning layer: it diagnoses saved
cold-start winner, control, and failure artifacts, proposes a versioned
`InformationScheme`, rebuilds anonymous blind packets from that scheme, and
evaluates whether the scheme separates historical winners from controls better
than the baseline blind prompt.

For the next research phase, Ralph must distinguish a broad
`ResearchInformationPlan` from the existing packet-level `InformationScheme`.
The research information plan answers what evidence to collect, where to obtain
it, how to extract atomic facts, which candidate signals or analysis rubrics to
derive, and how to validate representation quality. The current
`InformationScheme` remains the narrower proposal for section order, context
budgets, compression, and blind prompt/output contracts. Current code implements
mainly the narrow scheme layer; source coverage, atomic-fact fidelity, and
raw-versus-organized experiments are planned work rather than completed
capabilities.

The repository currently has no human-curated gold packet. Ralph must not refer
to any automatic packet, source audit, or limited manual fact check as gold, and
the next experiment must not depend on a gold-packet upper bound.

## External Interface

The submodule exposes:

- `InformationScheme`: a versioned, proposal-only structure describing blind
  packet section order, context budgets, required evidence buckets,
  compression rules, and contrary-evidence requirements.
- `BlindSchemePacket`: an anonymous as-of packet rendered from a
  `ResearchPacket` according to an `InformationScheme`.
- `RalphBlindResearcher`: protocol for evaluating a `BlindSchemePacket`
  without web tools.
- `HeuristicRalphBlindResearcher`: deterministic local validator for tests and
  dry runs.
- `OpenAIRalphBlindResearcher`: LLM-backed validator that sends only the
  scheme-rendered anonymous packet and uses no web-search tool.
- `CachedRalphBlindResearcher`: resumable wrapper that persists completed
  anonymous blind analyses by packet hash so larger OpenRouter runs can be
  interrupted and resumed without losing completed no-web judgments.
- `run_ralph_loop`: bounded 1-4 iteration loop for diagnosis, scheme proposal,
  scheme-packet construction, blind validation, evaluation, error analysis, and
  next-scheme proposal. Each failed iteration's next proposal becomes the
  actual scheme evaluated in the following iteration, so feedback is cumulative
  rather than only descriptive.
- `run_ralph_experiment`: artifact-backed refinement/holdout experiment. The
  scheme is refined on a small labeled refinement set, then evaluated once on a
  disjoint holdout set. The experiment is not considered successful unless the
  holdout blind metrics meet the separation threshold.
- `write_ralph_experiment_artifacts`: writes the refinement loop, holdout blind
  packets, holdout evaluation, holdout error analysis, and experiment manifest.

The next implementation should add research-level artifacts for information
requirements, source coverage, atomic evidence, raw-source blind packets,
raw-versus-organized comparison, information-family ablation/add-back results,
and layered failure attribution. These are proposal artifacts until their
schemas and implementation are reviewed; they do not change the current
production packet contract merely by appearing in this spec.

## Stage Contract

Ralph Loop v1 is connected only to formal cold-start / historical learning. It
does not run in daily monitoring, weekly scanning, watchlist publication, or
production default prompt assembly.

The loop has two trust boundaries:

1. Retrospective diagnosis and scheme synthesis. This stage may read known
   historical outcome groups, baseline blind analyses, signal observations,
   theme maps, playbooks, context coverage, and local cold-start artifacts. Its
   artifacts must be marked `retrospective_label_aware`.
2. Blind scheme validation. This stage rebuilds anonymous as-of packets from
   the proposed scheme and asks a blind researcher whether each anonymous case
   looks like a 3-6 month surge candidate. It must not receive ticker, company
   name, forward return, outcome group, post-as-of facts, source URLs, symbol-
   encoded ids, or web-search tools. Identity masking must cover common company
   name variants from merged/slash-separated names, class suffixes, and
   punctuation variants that can appear in document titles.

Inside those trust boundaries, the information-plan research cycle is:

1. Label-aware information discovery compares winner, control, and failure
   cases across T-180, T-120, T-90, T-60, T-30, and other approved as-of
   windows. It proposes information requirements, candidate signals, analysis
   rubrics, and `unclassified` evidence families instead of forcing every fact
   into the existing list.
2. Source-visible acquisition maps each requirement to supported APIs, SEC
   filings and exhibits, transcripts, news, investor materials, counterparty or
   industry evidence, point-in-time rules, and fallback sources. Missing states
   distinguish not found, not fetched, source unavailable, extraction failed,
   ambiguous, contradicted, and not applicable.
3. Atomic-fact extraction records subject, object or counterparty, event type,
   status, amount, unit, period, event date, publication date, source reference,
   and supporting span when applicable. Keyword presence alone is not a
   confirmed order, contract, customer, financing, strategic transaction,
   industry-chain transmission, or positive catalyst.
4. Signal and representation research derives measurable signal observations
   and analysis rubrics from atomic evidence, then renders versioned organized
   packets. Full raw source documents remain archived and traceable even when
   the blind packet is intentionally compressed.
5. Blind plain-LLM validation compares variants on a disjoint company holdout,
   attributes errors to the responsible layer, and returns only bounded
   proposals to the label-aware refinement set. A holdout used to generate a
   new proposal becomes retrospective feedback data and cannot independently
   validate that proposal.

Information requirements, signals, rubrics, and prompts are distinct. "Look for
actual order confirmation" is an information requirement or analysis rubric;
it becomes a signal only when the required source-linked facts and a repeatable
measurement or explicit qualitative observation are defined.

For small real experiments, Ralph must use a refinement/holdout split across
symbols. The label-aware diagnosis and initial scheme feedback may use the
refinement set first. The holdout set is evaluated with the final proposed
scheme and known labels are used only after blind outputs are produced. If the
holdout remains unseparated, the experiment may run a small bounded
holdout-feedback loop, explicitly marked
`retrospective_label_aware_holdout_feedback`, that feeds holdout error analysis
back into a next proposal and re-renders anonymous no-web holdout packets. This
feedback loop is an experimental proposal mechanism, not an independent
out-of-sample proof and not a production promotion rule. A run ending with
`holdout_not_separated` is a failed experiment, not a completed improvement.
When saved historical artifacts contain many thin packets, standalone
experiments may use an `evidence-rich` selection policy that still keeps
labels balanced but prioritizes latest cases with concrete catalyst, materiality,
risk, theme, fundamental, and market-confirmation content. This is a sampling
choice for research validation, not a production promotion rule.

## Next Experiment Contract

The next Ralph objective is to repair the evidence and evaluation problems
exposed by the July 7 12-company run, then identify an effective information
plan for a fixed plain-LLM baseline before any multi-agent analysis experiment.
The run showed anonymous no-web execution working, but winner and control
packets collapsed toward `insufficient_information`. Current evidence also
shows document-wide keyword matches can overstate orders, customers, AI-chain
transmission, financing, or strategic transactions; event types and polarity
can be wrong; multiple entities can be blended; numbers can lose units or
subjects; and repeated digests can create false corroboration across sections.

The next bounded experiment must:

1. Freeze the current v27 result and active scheme as the baseline; do not
   overwrite its packets or metrics.
2. Produce a versioned information-requirement inventory from label-aware
   cross-case and cross-window discovery. It must include an
   `other_or_unclassified` path for information outside the current ontology.
3. Produce a requirement-level source-coverage ledger before adding a new data
   API. The ledger must separate unavailable evidence from acquisition misses
   and extraction failures.
4. Replace document-wide keyword confirmation with source-linked atomic facts,
   entity roles, event-state and negation handling, normalized amount/unit/time
   fields, and deduplication. Fix extraction precision before increasing prompt
   volume or section budgets.
5. Compare the same anonymous point-in-time source bundle in two primary arms:
   a minimally processed raw-source packet and the organized packet. Both arms
   must use the same model, output schema, as-of cutoff, source set, and a
   documented context-budget policy. If the source bundle exceeds context,
   deterministic selection or chunking must be fixed before outcomes are seen.
6. Run targeted information-family add-back and ablation experiments for deal
   status/timing, capital structure/liquidity, orders/contracts,
   customer/capacity, policy/regulatory evidence, theme transmission, and
   expectation gap. Add-backs must contain actual sourced facts, not a prompt
   instruction that the facts would be useful.
7. Attribute each blind failure to `source_unavailable`, `acquisition_miss`,
   `extraction_error`, `signal_error`, `representation_loss`, `analysis_error`,
   or `not_predictably_supported_as_of`. An error may have multiple linked
   causes, but the report must identify the primary proposed intervention.
8. Refine only on labeled development cases, then validate once on a new
   untouched company holdout. Keep iterations bounded to one or two and return
   a next proposal instead of continuing automatically.

Raw-versus-organized comparison answers whether representation adds value; it
does not prove the source set is complete. Source-family discovery,
requirement-level coverage, unclassified-fact review, and add-back/ablation
experiments answer what information should be collected. Because no human gold
packet exists, Ralph may establish the best validated plan among tested sources,
budgets, and schemes, but must not claim a universal or information-complete
optimum.

## Information-Plan Exit Gate

Information-plan research is ready to hand off to analysis-method research only
when all of the following hold:

- anonymous point-in-time and no-web blind invariants pass, with no unresolved
  critical cross-case contamination or subject misattribution;
- requirement-level coverage and missing reasons are auditable, and sampled
  organized claims remain traceable to supporting source spans;
- the organized packet is compared fairly with the raw-source baseline and
  either provides useful, repeatable holdout separation or shows a stable
  representation plateau with residual failures attributed to analysis or
  irreducible as-of predictability rather than missing information;
- targeted add-backs and ablations no longer reveal a material, repeatable
  missing information family or representation loss on fresh holdouts;
- remaining errors are predominantly analysis or irreducible as-of
  predictability errors rather than acquisition, extraction, signal, or packet
  errors;
- the selected plan is versioned and remains proposal-only pending human
  review.

Exact evidence-fidelity, sample-size, and material-lift thresholds are research
design choices that must be confirmed before implementation. The existing v1
blind-separation threshold remains a compatibility gate, not sufficient proof
by itself that the broad information plan is complete. Multi-agent analysis may
begin only after this exit gate, using the same fixed information plan so any
gain is attributable to the analysis method.

The default v1 success threshold is quantitative:

- winner average positive-confidence minus control average positive-confidence
  is at least 0.12, where only `likely` and `possible` judgments contribute
  positive confidence;
- false-positive control rate is at most 0.25;
- false-negative winner rate is 0.00;
- blind packets remain anonymous, point-in-time, and no-web.
Artifacts may also keep the raw confidence gap for historical comparison, but
raw confidence is the model's confidence in its own judgment and must not be
interpreted as bullish confidence when the judgment is `unlikely` or
`insufficient_information`.
The blind prompt should align with this metric: `possible` is a positive
watchlist judgment and should only be used when source-backed positive evidence
supports confidence of at least 0.45. Lower-confidence positive hunches should
be returned as `insufficient_information` with missing evidence, not as
low-confidence `possible`.

If the holdout threshold is not met, Ralph must persist error analysis and a
next proposal. It must not present the loop as solved just because the bounded
iteration count was reached.

The default section priority for `InformationScheme` is:

1. Catalyst/Event Ledger
2. Expectation Gap Summary
3. Theme/Industry Transmission
4. Materiality and Timing
5. Contrary/Risk Evidence
6. Compressed Fundamentals
7. Compressed Market Confirmation

Raw technical indicators and basic financial tables are compressed context.
They must not dominate the packet budget or appear before catalyst,
expectation-gap, theme-transmission, materiality/timing, and risk evidence.
Recent source-backed events such as offerings, compliance plans, listing
changes, trading resumptions, merger deadlines, approvals, and earnings beats
should be rendered into `Materiality and Timing` with as-of-relative timing
rather than left only as raw news titles. When a price dislocation is visible
before source-backed events, `Expectation Gap Summary` may include a compact
market-implied expectation setup, but raw technical detail still belongs in the
compressed market-confirmation section.
Saved formal documents may be rehydrated into Ralph packets from local
`documents_and_catalysts.json` artifacts so current experiments can replace
old low-information filing excerpts with cleaned point-in-time source detail.
SEC/HTML boilerplate, inline-XBRL headers, and empty fragments must not be
treated as material evidence. Standalone Ralph experiments may optionally
refresh selected SEC filing bodies from already-saved SEC archive source URLs
before packet rendering. This refresh is data acquisition for the label-aware
research layer, not blind-stage web use. It must remain point-in-time by
filtering on document availability dates, must skip refreshed text that
introduces another selected case's identity tokens, and must pass global
cross-case leakage scanning before any external blind provider call. Refreshed
SEC primary documents must also be checked against their own declared
registrant and trading-symbol table; when those declared identities conflict
with the current case, the refreshed body is treated as a mismapped source and
the original local document is retained with an audit warning. For
AI-related evidence, `Theme/Industry Transmission` should map model/application
demand through compute, data-center, power, cooling, networking, component, and
customer-capex bottlenecks while explicitly distinguishing direct bottleneck
beneficiaries from broad AI-theme tourists.
The AI/theme transmission lens should render a compact stage map, including
matched chain stages, directness level, and company-level pull-through markers
such as orders, contracts, backlog, shipments, capacity, customer demand,
funding, capex, or guidance. Mentions of AI without these pull-through markers
must be shown as a theme-only caution, not promoted into a bullish catalyst.
Negated statements such as "no orders" or "no funding" must not be counted as
directness evidence.
The chain lens should follow a top-down methodology: identify the dominant
theme demand source, map the upstream and downstream bottleneck layers, decide
whether the anonymous company sits in a bottleneck or is merely theme-adjacent,
require source-backed proof of company-level pull-through, and then subtract
execution, financing, listing, and valuation risks. For AI/cloud cases, compact
digests should separately mark bottleneck position, direct evidence markers,
irreplaceability clues such as exclusive/proprietary/qualification/scarce-
capacity signals, and operating-leverage clues such as revenue, margin, EBITDA,
guidance, backlog conversion, shipments, or utilization. They may include
identity-safe references to enterprise digital transformation, cybersecurity
budgets, cloud-platform partnerships, customer or partner pull-through,
guidance, revenue, or EBITDA evidence, but only when those facts are available
point-in-time.
Ralph packets should also include a deterministic point-in-time event
distillation layer before raw source excerpts dominate the context. This layer
classifies saved as-of evidence into compact event families such as
orders/contracts, financing/capital, listing/compliance, strategic transaction,
policy/regulatory, governance/routine, earnings/results, capital return, and
AI-chain bottleneck transmission. Each distilled item records whether the event
looks positive, risk-heavy, mixed, routine, or uncertain from the as-of text, and
states the materiality lens or disqualifying risk. The distillation is blind-safe
because it reads only the anonymous packet evidence and is rendered into the
same masked blind packet; it must not use outcome labels or future returns.
Expectation-gap summaries should distinguish a depressed price plus a
source-backed positive event from a depressed price plus only routine or
risk-heavy filings.
Standalone Ralph experiments may derive compact `source_fact_digest` evidence
from already-saved local documents and optional refreshed SEC primary-document
text before rendering blind packets. These digests should extract auditable
point-in-time facts such as business/sector clues, revenue or sales, cash,
debt, stockholders' equity, listing-compliance terms, financing commitments, and
operating volumes without pasting raw tables. Listing digests should prefer
concrete terms such as minimum bid, stockholders' equity thresholds or deficits,
plan deadlines, and cure-period language; financing digests should prefer
drawn amounts, facility size, and covenant/liquidity context when available.
Strategic-transaction digests should extract Form F-4 or registration-statement
status, proposed business-combination language, shareholder approvals, merger
deadline extensions, possible extension windows, redemption language, proposed
listing plans, target-company revenue/EBITDA facts, and listing/tradability
risks when these are present in saved point-in-time documents. Risk sections
should receive a risk-focused digest so redemption, delisting/index-removal,
going-concern, dilution, debt, or liquidity facts are not truncated behind
positive operating facts.
They remain source-linked,
identity-masked at packet render time, and proposal-only; blind validation still
receives no web tools and no labels.
Because refreshed SEC filings often contain issuer, target, or counterparty
names not present in the original ticker profile, blind rendering must mask
counterparty names from merger-style titles and SEC issuer phrases such as
"X Inc. (the Company)" before preflight export. Experiment-only selection
controls may pin specified symbols into holdout or exclude suspected
cross-contaminating symbols; these controls are for Ralph validation only and do
not alter formal cold-start selection or any long-running default prompt.
Standalone experiments may also augment selected cases from SEC submissions
metadata by resolving the case to a CIK from already-saved SEC documents or the
SEC ticker mapping, selecting only filings available on or before the case
as-of date, and downloading a bounded number of primary documents. This is a
label-aware research-layer data acquisition step, not blind-stage web use.
Identity guards may allow same-CIK current and former registrant names or
trading symbols for extraction, but every such identity token must be masked
before blind-packet rendering and the global leakage preflight must pass before
any external blind provider call.

## Artifacts

Formal cold-start runs that execute Ralph Loop v1 write:

- `information_scheme.json`
- `ralph_loop_iterations.json`
- `blind_packets_by_scheme.json`
- `blind_scheme_evaluation.json`
- `ralph_error_analysis.json`

Standalone Ralph experiments also write:

- `ralph_experiment_summary.json`
- `holdout_blind_packets_by_scheme.json`
- `holdout_blind_scheme_evaluation.json`
- `holdout_error_analysis.json`
- `holdout_feedback_iterations.json`
- `case_selection_label_aware.json`
- `manifest.json`

The next information-plan experiment should add versioned proposal artifacts:

- `research_information_plan.json`
- `information_requirements.json`
- `evidence_coverage_ledger.json`
- `atomic_evidence_by_case.json`
- `raw_source_blind_packets.json`
- `raw_vs_organized_evaluation.json`
- `information_family_experiments.json`
- `layered_failure_attribution.json`

These filenames describe the intended next experiment contract. They are not
current outputs until the corresponding implementation and tests exist.

Before any external blind-LLM call, the standalone experiment runner can write
preflight artifacts without contacting a provider:

- `preflight_blind_llm_requests.json`
- `preflight_leakage_report.json`
- `preflight_scheme_diagnostic_label_aware.json`
- `preflight_manifest.json`

If blind responses are produced outside the current runtime, the experiment
runner can import them by `request_id` and write:

- `imported_blind_responses.json`
- `imported_blind_scheme_evaluation.json`
- `imported_error_analysis.json`
- `imported_next_scheme_proposal.json`
- `imported_response_manifest.json`

The run manifest records the Ralph artifact paths, active scheme version,
iteration count, warning count, and proposal-only status. The loop may also
append the latest proposal to local proposal memory under `.agent_state`, but it
must not overwrite production prompts or weekly/daily defaults.

The evaluation artifact keeps baseline and Ralph scheme results side by side:
winner/control confidence gaps, likely/possible distribution, false-positive
controls, false-negative winners, insufficient-information reasons, and error
analysis when separation remains weak.

Experiment summaries include the final status (`holdout_separated` or
`holdout_not_separated`), holdout positive-confidence gap, raw confidence gap
for comparison, false-positive rate,
false-negative rate, initial holdout evaluation, bounded holdout-feedback
iterations when enabled, and schema diffs between refinement proposals.
Preflight manifests must set `external_call_performed=false`, record packet
hashes, and pass leakage checks before an external provider run is attempted.
Leakage checks scan every packet for the current case's identity terms and for
all other selected cases' identity terms, because mismapped source documents can
otherwise leak a different sampled issuer into an anonymous packet.
Imported-response manifests must set `provider_call_performed_by_script=false`
and compute the same holdout pass/fail metrics before any scheme is considered
successful.

## Invariants

- The diagnostic phase may read historical outcome groups only because its
  artifacts are retrospective and label-aware.
- `InformationScheme` and `BlindSchemePacket` must not contain ticker, company
  name, source URLs, forward return, or outcome group values.
- Blind scheme validation must use only as-of packet contents and no web tools.
- Ralph proposals are prompt/information-structure candidates, not production
  defaults; human review is required before any long-running workflow consumes
  them.
- Old and new schemes must remain comparable in artifacts; do not overwrite the
  baseline blind analyses.
- A bounded Ralph run may stop because it hit the iteration cap, but only a
  passing holdout evaluation means the information scheme achieved the
  experiment goal.
- Ralph Loop is separate from measurable signal learning and from surge
  playbook synthesis. Signals describe what to measure; playbooks describe how
  to think; Ralph describes how to package information for blind assessment.
- Broad information-plan research may propose new requirements, signals, and
  rubrics, but each remains owned by its corresponding module and proposal
  boundary. Ralph coordinates their comparison; it does not silently promote
  or collapse them into prompt text.
- Raw sources are preserved as the audit layer. Organized packets may be lossy
  working representations, but every retained factual claim must remain
  traceable and representation loss must be measurable.
- No current artifact may be called a human gold packet. A future gold packet
  would require an explicit annotation protocol and separate approval.
- Multi-agent experiments must not begin by changing both the evidence plan and
  analyzer architecture in the same comparison.

## Testing

Tests should cover label-aware diagnostics, scheme and packet leakage checks,
section priority and compression, evaluation metrics, feedback proposal
generation, one-loop integration with fake artifacts and fake blind research,
refinement/holdout experiment artifacts, manifest paths, and no-web blind
prompt construction. The next implementation should also test requirement-level
missing states, source-span traceability, entity and event-state extraction,
negation, amount/unit preservation, deduplication, raw-versus-organized input
parity, holdout-consumption rules, layered failure attribution, and the absence
of any unsupported gold-packet claim.
