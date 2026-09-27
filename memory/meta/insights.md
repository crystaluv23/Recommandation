# Project Insights

- Test and script verification should use the bundled Python 3.11+ runtime with `PYTHONPATH=src`; macOS system `python3` can be Python 3.9 and fail on existing 3.11+ syntax/imports before tests execute.
- Formal cold-start work should begin by restating the execution contract and auditing the exact runner inputs/prompt JSON; existing scaffolding can hide missing packet data, identity leaks, and seed/formal entry-point drift.

## Self-evolution review discipline (2026-09-27)

- Before another Fast/Slow repair or live successor, consult [self-evolution convergence and acceptance](../experiences/self-evolution-convergence-and-acceptance.md). Start from the accumulated failure trajectory and explain why the earlier check missed the current same-class defect.
- Separate reliable execution, correct feedback consumption, and independent research gain. A committed cycle can contain failed subgoals; a Signal can be promoted without being used; use does not prove benefit. Tests and local replay never prove a live successor completed.
- Validate real producer-to-consumer record shapes and real production construction. Do not mock the integration boundary under acceptance. Include post-commit work, restart, imported history, next-cycle reads, and context growth when those paths are affected.
- Classify upstream data, protocol, execution, and capability failures before generating research lessons. Keep their cost in formal frozen-cohort results while preventing synthetic technical abstentions from becoming invented research causes.
- Preserve full immutable history, but treat a bounded model-facing read view as a separate design problem. Current additive-history constraints must be reviewed top-down before introducing projections; no silent truncation, history deletion, or budget-only workaround.
- Converge on a comparable baseline before adding more mechanisms. Use the existing independent paired/four-arm confirmation contract to judge gain. If reliable independent evaluation still finds no gain, revisit the research hypothesis rather than endlessly extending guards.

Evidence and qualifications: [multi-iteration retrospective](../../reports/self-evolution-retrospective-20260927.md). These are work and reporting rules, not newly implemented runtime gates or changed scoring/promotion semantics.
