# Changelog

- 2026-05-02: Migrated the meta mechanism from `../Quant` into this repository as a target-neutral setup: session entry, spec guide, progress tracking, and memory protocol are initialized without carrying over quant-specific assumptions.
- 2026-05-02: Added a git checkpoint discipline requiring assistant-made project changes to be staged and committed once before the final reply for easier rollback.
- 2026-05-02: Added a tracked pre-push lint hook, reusable repository lint command, and ignored local lint feedback logs for assistant self-feedback after push checks.
- 2026-05-02: Replaced target placeholders with the stock opportunity agent vision and architecture, then drafted module-level specs for the future `stock_opportunity_agent` package.
- 2026-05-02: Added the rule that materially ambiguous research-design choices should be confirmed with the user at module implementation time and then recorded in the relevant spec.
- 2026-05-02: Expanded the spec architecture into an isomorphic package/submodule tree that mirrors the intended future `src/stock_opportunity_agent/` code layout.
- 2026-05-02: Rechecked the architecture against the system-design discussion and pruned premature child specs into `spec/_archive/`, keeping the active tree at module-level boundaries until implementation proves finer splits.
- 2026-05-02: Integrated transferable code quality requirements from `../Prediction/AGENTS.md` into this project's session entry point.
- 2026-05-02: Added the initial Python package skeleton with domain records, validated config loading, registry-based OpenAI model provider, registry-based data-source providers, SEC EDGAR and Alpha Vantage adapters, and unit tests.
- 2026-05-02: Moved the LLM provider registry from `research.models` to top-level `llm` so provider adapters are not coupled to the research module.
- 2026-05-02: Expanded the data-source layer with a capability rationalization, active `data/sources` spec, source preference plan, and SEC EDGAR, Stooq, Alpha Vantage, FRED, OpenFIGI, and Finnhub adapters.
- 2026-05-02: Added data-source runtime state with a raw response cache, request ledger, source quota checks, and a managed transport that defers quota-exhausted free API calls without sleeping.
- 2026-05-02: Added ignore rules for local environment and agent-state files so user-provided API keys and cached raw data remain untracked.
- 2026-05-03: Folded the earlier cold-start discussion into the active architecture by making current universe state and novelty/anomaly detection explicit within existing memory, signal, scanner, monitoring, and orchestration specs.
- 2026-05-02: Implemented the post-source data layer with structured feature normalization, document as-of retrieval/chunking, point-in-time research packet assembly, and `FeatureRecord` packet support.
