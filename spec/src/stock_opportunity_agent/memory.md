# Memory

## Status
Started

## Purpose

Persist long-term local memory so the agent can remember companies, theses, signals, themes, decisions, reviews, and lessons across runs.

## External Interface

Memory collections should include:

- Company Memory
- Thesis Memory
- Signal Memory
- Case Memory
- Decision Memory
- Current Universe Store
- Review Memory
- Theme Memory
- Segment Memory
- Research Playbook Memory
- Information Scheme Proposal Memory
- Experiment Memory
- User Preference Memory

The module should expose repository-style interfaces for reading, writing, querying, and versioning these records.

Active child specs:

- [`memory/knowledge.md`](memory/knowledge.md): shared Experience/Signal use
  contexts and deterministic committed-history performance summaries.
- [`memory/signals.md`](memory/signals.md): file-backed local signal library
  for cold-start promoted signal definitions and learned signal logic.
- [`memory/themes.md`](memory/themes.md): file-backed local theme library for
  cold-start industry-chain maps.
- [`memory/playbooks.md`](memory/playbooks.md): file-backed local playbook
  library for cold-start surge-research thinking patterns.

## Collection Semantics

- Company Memory stores durable company context, key drivers, known risks, and prior research summaries so future runs do not rediscover basic context from scratch.
- Thesis Memory stores active and archived claims with evidence, catalysts, validation contracts, disconfirming conditions, status, and review dates. The durable object is the thesis, not merely the ticker.
- Signal Memory stores signal definitions, applicability, historical performance, false-positive patterns, counterexamples, and hindsight-risk notes.
- Case Memory stores historical winners, matched controls, failures, stale-watchlist cases, as-of slices, blind-analysis outputs, and postmortem lessons.
- Decision Memory stores each ranked output with run id, rank, scores, recommendation state, reason, linked thesis, linked validation contract when required, data snapshot, prompt version, scoring version, model version, and signal-library version.
- Current Universe Store stores operational ticker state: last analysis date, latest score, active thesis summary, material new information, and reanalysis need.
- Review Memory stores 1-month, 3-month, and 6-month outcomes, earnings validation reports, thesis validation, error labels, what worked, what failed, and lessons.
- Theme Memory stores theme maps, current bottlenecks, leading indicators, and review history.
- Segment Memory stores theme-segment stage history, candidate tickers, validation evidence, false signals, and crowdedness or valuation warnings.
- Research Playbook Memory stores reusable research questions, reasoning steps,
  positive/counter patterns, false-positive traps, linked signals, linked
  themes, and hindsight-risk notes.
- Information Scheme Proposal Memory stores proposal-only Ralph Loop
  `InformationScheme` versions, their source run ids, evaluation summaries, and
  approval state. It must not act as the production prompt store.
- Experiment Memory stores meta-learning hypotheses, experiment designs, results, approval states, and promoted or rejected versions.
- User Preference Memory stores explicit user preferences about scope, cadence, risk tolerance for research output, sectors, and reporting style; it must not be inferred from unstated trading intent.

## Responsibilities

- Store every watchlist decision with its evidence, scores, and version stamps.
- Store every high-priority thesis with a validation contract that future monitoring and review can evaluate.
- Store current ticker state, including last analysis date, latest score, thesis summary, changed information, and whether reanalysis is needed.
- Store active and archived theses separately by status.
- Track signal performance and false-positive patterns.
- Track Experience performance after explicit Plan adoption, and expose the same
  bounded applicability/failure/performance vocabulary on both knowledge briefs.
- Track theme and segment stage histories.
- Track reusable research playbooks that can later inform prompt proposals.
- Track Ralph Loop information-scheme proposals separately from production
  prompt defaults.
- Preserve error labels and lessons from reviews.
- Support retrieval of relevant prior memory for research packets.

## Dependencies

- Uses `models` for durable records.
- Uses `config` for storage locations.
- Feeds research, scoring, monitoring, review, meta-learning, and reports.

## Invariants

- Memory is not a chat transcript; it stores structured research history.
- A thesis belongs to a claim and evidence set, not just a ticker.
- A validation contract belongs to the thesis and decision that created it; later reviews may mark it validated, weakened, broken, or stale, but must not edit away the original expected metrics.
- Failed recommendations must remain queryable.
- Current universe state is operational memory; it can be refreshed, but its changes must still be traceable to data updates, monitoring events, or completed runs.
- Memory updates should be append-friendly; destructive rewrites require explicit migration or human approval.
- Records must be traceable back to the run or review that created them.

## Testing

Tests should cover create/read/update/archive flows, idempotent writes, query filters, version tracking, and preservation of failed decisions.
