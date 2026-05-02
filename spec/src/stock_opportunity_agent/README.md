# Stock Opportunity Agent Specs

## Status
Done

This directory mirrors the intended future source package `src/stock_opportunity_agent/`.

The files here are module-level contracts. They are more concrete than `spec/architecture.md`, but still avoid implementation details such as exact table DDL, vendor SDKs, or final prompt wording until implementation begins.

## Intended Isomorphic Tree

```text
src/stock_opportunity_agent/
  models/
    records.py
    enums.py
    validation.py
  config/
    schemas.py
    loader.py
  data/
    sources.py
    structured.py
    documents.py
    point_in_time.py
  memory/
    stores.py
    repositories.py
    retrieval.py
  themes/
    discovery.py
    chain_map.py
    segment_scoring.py
  cases/
    labeling.py
    controls.py
    packets.py
    analysis.py
  signals/
    definitions.py
    measurement.py
    evaluation.py
  scanner/
    universe.py
    filters.py
    candidates.py
  research/
    agents.py
    prompts.py
    schemas.py
  scoring/
    rocket.py
    theme_scores.py
    risk.py
  ranking/
    cross_section.py
    changes.py
  monitoring/
    events.py
    state_machine.py
  review/
    outcomes.py
    errors.py
    attribution.py
  meta_learning/
    evaluation.py
    experiments.py
    proposals.py
    versions.py
  reports/
    watchlist.py
    cards.py
    reviews.py
  orchestration/
    pipelines.py
    manifests.py
```

The matching spec tree is:

```text
spec/src/stock_opportunity_agent/
  models.md
  models/
    records.md
    enums.md
    validation.md
  config.md
  config/
    schemas.md
    loader.md
  data.md
  data/
    sources.md
    structured.md
    documents.md
    point_in_time.md
  memory.md
  memory/
    stores.md
    repositories.md
    retrieval.md
  themes.md
  themes/
    discovery.md
    chain_map.md
    segment_scoring.md
  cases.md
  cases/
    labeling.md
    controls.md
    packets.md
    analysis.md
  signals.md
  signals/
    definitions.md
    measurement.md
    evaluation.md
  scanner.md
  scanner/
    universe.md
    filters.md
    candidates.md
  research.md
  research/
    agents.md
    prompts.md
    schemas.md
  scoring.md
  scoring/
    rocket.md
    theme_scores.md
    risk.md
  ranking.md
  ranking/
    cross_section.md
    changes.md
  monitoring.md
  monitoring/
    events.md
    state_machine.md
  review.md
  review/
    outcomes.md
    errors.md
    attribution.md
  meta_learning.md
  meta_learning/
    evaluation.md
    experiments.md
    proposals.md
    versions.md
  reports.md
  reports/
    watchlist.md
    cards.md
    reviews.md
  orchestration.md
  orchestration/
    pipelines.md
    manifests.md
```

## Module Groups

Foundation:

- [`models.md`](models.md), with child specs under [`models/`](models/).
- [`config.md`](config.md), with child specs under [`config/`](config/).
- [`data.md`](data.md), with child specs under [`data/`](data/).
- [`memory.md`](memory.md), with child specs under [`memory/`](memory/).

Research and discovery:

- [`themes.md`](themes.md), with child specs under [`themes/`](themes/).
- [`cases.md`](cases.md), with child specs under [`cases/`](cases/).
- [`signals.md`](signals.md), with child specs under [`signals/`](signals/).
- [`scanner.md`](scanner.md), with child specs under [`scanner/`](scanner/).
- [`research.md`](research.md), with child specs under [`research/`](research/).

Decision output:

- [`scoring.md`](scoring.md), with child specs under [`scoring/`](scoring/).
- [`ranking.md`](ranking.md), with child specs under [`ranking/`](ranking/).
- [`monitoring.md`](monitoring.md), with child specs under [`monitoring/`](monitoring/).
- [`reports.md`](reports.md), with child specs under [`reports/`](reports/).

Learning loops:

- [`review.md`](review.md), with child specs under [`review/`](review/).
- [`meta_learning.md`](meta_learning.md), with child specs under [`meta_learning/`](meta_learning/).
- [`orchestration.md`](orchestration.md), with child specs under [`orchestration/`](orchestration/).
