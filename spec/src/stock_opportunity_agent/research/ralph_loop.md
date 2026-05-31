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
- `run_ralph_loop`: bounded 1-2 iteration loop for diagnosis, scheme proposal,
  scheme-packet construction, blind validation, evaluation, error analysis, and
  next-scheme proposal.

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
   encoded ids, or web-search tools.

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

## Artifacts

Formal cold-start runs that execute Ralph Loop v1 write:

- `information_scheme.json`
- `ralph_loop_iterations.json`
- `blind_packets_by_scheme.json`
- `blind_scheme_evaluation.json`
- `ralph_error_analysis.json`

The run manifest records the Ralph artifact paths, active scheme version,
iteration count, warning count, and proposal-only status. The loop may also
append the latest proposal to local proposal memory under `.agent_state`, but it
must not overwrite production prompts or weekly/daily defaults.

The evaluation artifact keeps baseline and Ralph scheme results side by side:
winner/control confidence gaps, likely/possible distribution, false-positive
controls, false-negative winners, insufficient-information reasons, and error
analysis when separation remains weak.

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
- Ralph Loop is separate from measurable signal learning and from surge
  playbook synthesis. Signals describe what to measure; playbooks describe how
  to think; Ralph describes how to package information for blind assessment.

## Testing

Tests should cover label-aware diagnostics, scheme and packet leakage checks,
section priority and compression, evaluation metrics, feedback proposal
generation, one-loop integration with fake artifacts and fake blind research,
manifest paths, and no-web blind prompt construction.
