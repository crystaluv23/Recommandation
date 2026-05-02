# Stock Opportunity Agent Specs

## Status
Done

This directory mirrors the intended future source package `src/stock_opportunity_agent/`.

The files here are module-level contracts. They are more concrete than `spec/architecture.md`, but still avoid implementation details such as exact table DDL, vendor SDKs, or final prompt wording until implementation begins.

## Module Groups

Foundation:

- [`models.md`](models.md)
- [`config.md`](config.md)
- [`data.md`](data.md)
- [`memory.md`](memory.md)

Research and discovery:

- [`themes.md`](themes.md)
- [`cases.md`](cases.md)
- [`signals.md`](signals.md)
- [`scanner.md`](scanner.md)
- [`research.md`](research.md)

Decision output:

- [`scoring.md`](scoring.md)
- [`ranking.md`](ranking.md)
- [`monitoring.md`](monitoring.md)
- [`reports.md`](reports.md)

Learning loops:

- [`review.md`](review.md)
- [`meta_learning.md`](meta_learning.md)
- [`orchestration.md`](orchestration.md)
