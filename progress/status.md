# Status

| Area | Spec | Code | Status | Notes |
| --- | --- | --- | --- | --- |
| Meta mechanism | [`AGENTS.md`](../AGENTS.md), [`spec/README.md`](../spec/README.md) | [`scripts/lint_repo.sh`](../scripts/lint_repo.sh), [`.githooks/pre-push`](../.githooks/pre-push) | Done | Session entry, spec discipline, progress, memory hygiene, git checkpoint discipline, and pre-push lint feedback are active. |
| Vision | [`spec/vision.md`](../spec/vision.md) | None | Spec Done | Defines the project as a 3-6 month stock opportunity discovery agent that outputs watchlists, not trades. |
| Architecture | [`spec/architecture.md`](../spec/architecture.md) | None | Spec Done | Defines the local-first, auditable architecture across data, memory, theme transmission, research, scoring, review, and meta-learning. |
| Spec module map | [`spec/src/stock_opportunity_agent/README.md`](../spec/src/stock_opportunity_agent/README.md) | None | Spec Done | Establishes an isomorphic intended source/spec tree for the future `stock_opportunity_agent` package. |
| Models | [`spec/src/stock_opportunity_agent/models.md`](../spec/src/stock_opportunity_agent/models.md) | None | Spec Done | Shared records for packets, theses, scores, decisions, reviews, experiments, and versions. |
| Config | [`spec/src/stock_opportunity_agent/config.md`](../spec/src/stock_opportunity_agent/config.md) | None | Spec Done | Universe, data-source, storage, scoring, prompt, pipeline, and meta-learning policy configuration. |
| Data | [`spec/src/stock_opportunity_agent/data.md`](../spec/src/stock_opportunity_agent/data.md) | None | Spec Done | Structured and unstructured data access with point-in-time packet construction. |
| Memory | [`spec/src/stock_opportunity_agent/memory.md`](../spec/src/stock_opportunity_agent/memory.md) | None | Spec Done | Local long-term memory for companies, theses, signals, cases, decisions, reviews, themes, segments, experiments, and preferences. |
| Themes | [`spec/src/stock_opportunity_agent/themes.md`](../spec/src/stock_opportunity_agent/themes.md) | None | Spec Done | Theme discovery, industry-chain maps, transmission stage, and segment timing. |
| Cases | [`spec/src/stock_opportunity_agent/cases.md`](../spec/src/stock_opportunity_agent/cases.md) | None | Spec Done | Historical winner, control, failure, and blind point-in-time case learning. |
| Signals | [`spec/src/stock_opportunity_agent/signals.md`](../spec/src/stock_opportunity_agent/signals.md) | None | Spec Done | Versioned signal library, measurement, applicability, and performance tracking. |
| Scanner | [`spec/src/stock_opportunity_agent/scanner.md`](../spec/src/stock_opportunity_agent/scanner.md) | None | Spec Done | Non-LLM universe filtering and candidate generation before expensive research. |
| Research | [`spec/src/stock_opportunity_agent/research.md`](../spec/src/stock_opportunity_agent/research.md) | None | Spec Done | LLM research, skeptic, theme, valuation, and judge roles with structured outputs. |
| Scoring | [`spec/src/stock_opportunity_agent/scoring.md`](../spec/src/stock_opportunity_agent/scoring.md) | None | Spec Done | Theme Transmission, Segment Timing, Rocket Score, risk penalty, and final opportunity score. |
| Ranking | [`spec/src/stock_opportunity_agent/ranking.md`](../spec/src/stock_opportunity_agent/ranking.md) | None | Spec Done | Segment-level and cross-market watchlist ranking with change explanations. |
| Monitoring | [`spec/src/stock_opportunity_agent/monitoring.md`](../spec/src/stock_opportunity_agent/monitoring.md) | None | Spec Done | Catalyst monitoring and watchlist state transitions. |
| Review | [`spec/src/stock_opportunity_agent/review.md`](../spec/src/stock_opportunity_agent/review.md) | None | Spec Done | Outcome tracking, thesis validation, error labeling, and signal attribution. |
| Meta-learning | [`spec/src/stock_opportunity_agent/meta_learning.md`](../spec/src/stock_opportunity_agent/meta_learning.md) | None | Spec Done | System-level performance evaluation, hypotheses, experiments, version comparison, and controlled change proposals. |
| Reports | [`spec/src/stock_opportunity_agent/reports.md`](../spec/src/stock_opportunity_agent/reports.md) | None | Spec Done | Weekly watchlists, company cards, theme maps, reviews, meta-learning reports, and audit bundles. |
| Orchestration | [`spec/src/stock_opportunity_agent/orchestration.md`](../spec/src/stock_opportunity_agent/orchestration.md) | None | Spec Done | Cold-start, daily, weekly, monthly, quarterly, and manual research pipelines. |

Next step: implement a minimal package skeleton and the core model/config layer, then add tests around serialization, config validation, and run manifests.
