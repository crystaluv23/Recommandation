# Changelog

- 2026-05-02: Migrated the meta mechanism from `../Quant` into this repository as a target-neutral setup: session entry, spec guide, progress tracking, and memory protocol are initialized without carrying over quant-specific assumptions.
- 2026-05-02: Added a git checkpoint discipline requiring assistant-made project changes to be staged and committed once before the final reply for easier rollback.
- 2026-05-02: Added a tracked pre-push lint hook, reusable repository lint command, and ignored local lint feedback logs for assistant self-feedback after push checks.
- 2026-05-02: Replaced target placeholders with the stock opportunity agent vision and architecture, then drafted module-level specs for the future `stock_opportunity_agent` package.
- 2026-05-02: Added the rule that materially ambiguous research-design choices should be confirmed with the user at module implementation time and then recorded in the relevant spec.
