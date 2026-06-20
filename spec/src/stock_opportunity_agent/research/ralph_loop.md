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

## Stage Contract

Ralph Loop v1 is connected only to formal cold-start / historical learning. It
does not run in daily monitoring, weekly scanning, watchlist publication, or
production default prompt assembly.

The loop has two phases:

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

The default v1 success threshold is quantitative:

- winner average confidence minus control average confidence is at least 0.12;
- false-positive control rate is at most 0.25;
- false-negative winner rate is 0.00;
- blind packets remain anonymous, point-in-time, and no-web.

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
treated as material evidence. For AI-related evidence, `Theme/Industry
Transmission` should map model/application demand through compute, data-center,
power, cooling, networking, component, and customer-capex bottlenecks while
explicitly distinguishing direct bottleneck beneficiaries from broad AI-theme
tourists.

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
`holdout_not_separated`), holdout confidence gap, false-positive rate,
false-negative rate, initial holdout evaluation, bounded holdout-feedback
iterations when enabled, and schema diffs between refinement proposals.
Preflight manifests must set `external_call_performed=false`, record packet
hashes, and pass leakage checks before an external provider run is attempted.
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

## Testing

Tests should cover label-aware diagnostics, scheme and packet leakage checks,
section priority and compression, evaluation metrics, feedback proposal
generation, one-loop integration with fake artifacts and fake blind research,
refinement/holdout experiment artifacts, manifest paths, and no-web blind
prompt construction.
