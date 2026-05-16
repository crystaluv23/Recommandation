# Stock Opportunity Agent Specs

## Status
Done

This directory defines the active module-level contracts for the future `stock_opportunity_agent` package.

The current architecture is deliberately lean: active specs stay at module level unless implementation has proved a child boundary. The data layer has active child specs because provider adapters, structured feature normalization, document retrieval, and point-in-time packet assembly already exist as separate code boundaries. Other module names below may later become single Python files or packages, but the spec tree does not force that choice before implementation proves the boundary.

Earlier pre-implementation child specs were archived under [`../../_archive/2026-05-02-preimplementation-submodule-specs/`](../../_archive/2026-05-02-preimplementation-submodule-specs/). They are historical notes, not active architecture.

## Active Intended Tree

```text
src/stock_opportunity_agent/
  models
  config
  data
    sources
    structured
    documents
    point_in_time
  memory
    signals
    themes
    playbooks
  themes
  cases
  signals
  scanner
  research
    cold_start
    inflection_discovery
    evidence_acquisition
    playbooks
  scoring
  ranking
  monitoring
  review
  meta_learning
  reports
  orchestration
```

Matching active specs:

```text
spec/src/stock_opportunity_agent/
  models.md
  config.md
  data.md
  data/sources.md
  data/structured.md
  data/documents.md
  data/point_in_time.md
  memory.md
  memory/signals.md
  memory/themes.md
  memory/playbooks.md
  themes.md
  cases.md
  signals.md
  scanner.md
  research.md
  research/cold_start.md
  research/inflection_discovery.md
  research/evidence_acquisition.md
  research/playbooks.md
  scoring.md
  ranking.md
  monitoring.md
  review.md
  meta_learning.md
  reports.md
  orchestration.md
```

## Design Coverage

The active module set reflects the system-design discussion without turning every future helper into an entity:

- The thesis-centered loop, expectation-gap research, watchlist output, validation contracts, and recommendation/trading separation live in [`vision.md`](../../vision.md) and [`architecture.md`](../../architecture.md).
- Point-in-time data, structured data as backbone, and document retrieval live in [`data.md`](data.md), with active child contracts for provider adapters in [`data/sources.md`](data/sources.md), feature normalization in [`data/structured.md`](data/structured.md), document retrieval in [`data/documents.md`](data/documents.md), and packet construction in [`data/point_in_time.md`](data/point_in_time.md).
- Local long-term memory for companies, theses, signals, cases, decisions, reviews, current universe state, themes, research playbooks, segments, experiments, and preferences lives in [`memory.md`](memory.md).
- Historical winners, controls, failures, and blind analysis packets live in [`cases.md`](cases.md).
- Theme discovery, industry-chain transmission, segment stage, and timing live in [`themes.md`](themes.md).
- Signal definitions, novelty/anomaly detection, and performance learning live in [`signals.md`](signals.md).
- Non-LLM coarse screening, current-state-aware rerun selection, and anomaly-driven candidate surfacing before expensive research live in [`scanner.md`](scanner.md).
- LLM research, skeptic passes, valuation critique, evidence-for/evidence-against, cold-start playbook synthesis, validation-contract drafting, and structured thesis output live in [`research.md`](research.md).
- Theme scores, Segment Timing, Company Rocket Score, Launch Probability, Upside Potential, and risk adjustment live in [`scoring.md`](scoring.md).
- Segment-level and market-level comparison live in [`ranking.md`](ranking.md).
- Catalyst triggers, validation-contract checks, and watchlist state transitions live in [`monitoring.md`](monitoring.md).
- Outcome tracking, earnings validation, error labeling, thesis validation, and signal attribution live in [`review.md`](review.md).
- Meta-learning, experiments, version comparison, and controlled change proposals live in [`meta_learning.md`](meta_learning.md).
- Human-facing watchlists, cards, reviews, and audit bundles live in [`reports.md`](reports.md).
- Cold-start, daily, weekly, monthly, quarterly, and manual workflows live in [`orchestration.md`](orchestration.md).

## Occam Boundary Rule

Add a child spec only when:

- another module needs a stable interface from that submodule,
- the parent spec grows beyond about 150 lines and has separable concerns, or
- implementation has already created a source package whose internal modules need different invariants or tests.

Until then, keep the boundary inside the parent spec. This prevents the design from mistaking a plausible future helper for a necessary system entity.
