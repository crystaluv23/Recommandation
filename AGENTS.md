# Stock Opportunity Agent - Session Entry Point

> Read this file first at the start of every session. It should take under 2 minutes.

## What this project is

This project is a long-running stock opportunity discovery and thesis-management agent.

It is designed to find US-listed stocks that may be repriced over the next 3-6 months because of expectation gaps, industry-chain transmission, catalysts, and early market confirmation. It produces watchlists, research cards, thesis records, and review artifacts. It does not produce automatic buy/sell orders.

-> See [`spec/vision.md`](spec/vision.md) for goals, non-goals, and design principles.
-> See [`spec/architecture.md`](spec/architecture.md) for the top-level design.

## Where things stand right now

-> See [`progress/status.md`](progress/status.md) for current done / doing / blocked / next.

## Memory (load on demand)

Accumulated experience and meta-learning live in `memory/`. When prior experience might apply, read [`memory/GUIDE.md`](memory/GUIDE.md) - it contains the index and protocol. Do not read it at session start.

---

## File Architecture

```text
AGENTS.md                   <- you are here (session entry point)
spec/                       <- design layer (hierarchical, module-level)
  vision.md                 <- goals, non-goals, principles
  architecture.md           <- top-level framework design
  README.md                 <- spec conventions
  src/
    stock_opportunity_agent/
      <module>.md           <- package/module spec, created before implementation
      <module>/
        <submodule>.md      <- sub-module spec when future source has a submodule
memory/                     <- accumulated learning (read on demand, not by default)
  GUIDE.md                  <- entry point: experience index + visit_times protocol
  experiences/              <- concrete lessons: bugs, anti-patterns, decisions
  meta/
    insights.md             <- distilled project-specific advice
    usage_log.md            <- raw log of experience reads + meta-review records
progress/                   <- live project state
  status.md                 <- module-by-module progress table
  changelog.md              <- running log of meaningful changes
scripts/                    <- repository maintenance commands
src/                        <- source code, once implementation begins
tests/                      <- tests, mirroring source structure when practical
```

## Core Conventions

**Target discipline:**
The target is a stock opportunity discovery agent, not an automatic trading system. Keep research, scoring, memory, and review concerns separate from execution, brokerage, leverage, and position sizing. If future work crosses into trading automation, stop and ask for explicit user confirmation before designing or implementing it.

**Spec hierarchy:**
`spec/vision.md` -> `spec/architecture.md` -> module specs under `spec/src/` -> sub-module specs.
Each level is progressively more concrete. Once source code exists, module specs should be written or expanded before implementation begins.

**Tree consistency rule:**
If a proposed spec change conflicts with a constraint in an ancestor spec (`architecture.md` or `vision.md`), stop. Name the exact ancestor level where the conflict arises, explain it to the user, and wait for confirmation before proceeding. Propagate confirmed changes top-down.

**Sync discipline:**
If design changes mid-session, update the spec first or simultaneously. Spec and code diverging within a session is a bug. If code changes are exploratory, backfill the spec before ending the session.

**Before implementing:**
State assumptions explicitly. If the target or user intent is still genuinely unclear, ask one focused question. If a simple conservative interpretation is available, use it and document the assumption.

**Research-design clarification:**
The specs intentionally leave some research choices open until the relevant module is implemented. When a detail has multiple reasonable definitions and could materially affect results, ask the user before coding it. Examples include winner labels, control-group matching criteria, point-in-time cutoffs, scoring weights, theme-stage thresholds, signal promotion rules, and meta-learning approval boundaries. After the user confirms, record the decision in the module spec before or alongside implementation.

**Architecture before implementation:**
Read the relevant module spec before working on a module; it carries the interface contract and design decisions. Read `spec/vision.md` when a decision involves trade-offs against project goals, such as coverage versus precision, auditability versus convenience, or research depth versus cost. Changes that look local can have non-local consequences in data lineage, scoring, review, and meta-learning.

**Code quality norms:**
- Write the minimum code that solves the problem. No abstractions for single-use code, no "flexibility" or "configurability" that was not requested. If a solution grows far beyond its apparent job, stop and simplify before continuing.
- Modules and public functions carry docstrings. Include a usage example when behavior is not self-evident from the signature alone.
- Keep modules loosely coupled and shaped around explicit interfaces. A unit should do one thing, and dependencies should flow in one direction.
- Names should reveal intention at the shortest length that is unambiguous in context. Use longer names only when the shorter one would genuinely mislead.
- Match the repository's established style once code exists.
- Write unit tests under `tests/` mirroring `src/` where practical. Cover deterministic model, config, parsing, scoring, and pipeline behavior with unit tests; validate LLM-heavy research quality through review/evaluation artifacts rather than brittle unit assertions.
- Add tests in proportion to risk and blast radius.

**Dependency hygiene:**
When a runtime and packaging format exist, keep dependency declarations as the source of truth for that ecosystem. Do not leave undeclared runtime imports or packages. If the target later becomes Python, prefer `pyproject.toml` as the canonical runtime dependency declaration and keep `requirements.txt` thin if one is used.

**Surgical changes:**
Touch only what the task requires. Do not improve adjacent code, comments, or formatting. Remove dead code and redundancy that your changes created. For pre-existing unrelated issues, mention them rather than fixing them silently.

**Decision scope:**
Decide autonomously within a module's implementation on ordinary algorithms, error handling, data structures, and library choices when they honor the relevant spec. Surface to the user before acting on anything that changes a module's interface contract, introduces a new cross-module dependency not described in `spec/architecture.md`, changes canonical record schemas or scoring semantics, alters point-in-time data guarantees, or moves the project toward trading automation.

**Architecture invariants - never violate in code:**
- Keep research, scoring, memory, review, reporting, and orchestration concerns separated along the boundaries in `spec/architecture.md`.
- Preserve point-in-time data discipline: do not let future data, revised facts, or post-outcome labels leak into candidate generation, scoring, historical cases, or evaluations unless the artifact is explicitly marked as retrospective review.
- Do not make brokerage, order placement, leverage, or position-sizing behavior part of the system without explicit user confirmation and a top-down spec update.
- Do not change canonical thesis, score, decision, review, experiment, or version records without updating the owning module spec and checking ancestor-spec implications.

**Memory protocol:**
Do not read memory at session start. When you encounter a situation where prior experience might apply, open `memory/GUIDE.md` and follow the consultation protocol. When starting work on a specific module after modules exist, do a quick trigger-map scan before diving in.

**Progress hygiene:**
For any session where code or design changes, fix spec drift, update `progress/status.md`, append a line to `progress/changelog.md`, and add memory only for non-obvious lessons likely to matter later.

**Git checkpoint discipline:**
Whenever the assistant changes project files during a conversation turn, it must create one git checkpoint before the final reply. Inspect `git status`, stage only the files changed for the current task unless the user explicitly asks otherwise, and run `git commit` with a concise message. Do not commit unrelated user changes. If verification could not be run or failed, mention that in the final reply while still keeping the committed checkpoint useful for rollback.

**Pre-push lint feedback:**
The repository uses tracked git hooks from `.githooks/`; local git config should set `core.hooksPath` to `.githooks`. Before every push, `.githooks/pre-push` runs `scripts/lint_repo.sh`. The hook prints the result and writes the latest full output to `.lint-feedback/pre-push-last.log`, with history in `.lint-feedback/pre-push-history.log`. After any push attempt or manual pre-push lint run, the assistant must read or account for that latest result before reporting back, and fix current-task lint failures before pushing.

---

## Workflows

### Multi-step tasks

_Trigger: any task with 3+ non-trivial steps._

Before starting, state verifiable success criteria.

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
```

### Starting a new module

_Trigger: you are about to implement a module that has no spec yet._

1. Read `spec/architecture.md` and confirm where the module sits.
2. Draft `spec/src/<package>/<module>.md` or the nearest appropriate module spec.
3. Add or update the relevant row in `progress/status.md`.
4. Add source annotations only if the language and local conventions make that natural.

### Session end

_Trigger: any session where code or design was changed._

1. Sync specs with code and design.
2. Update `progress/status.md`.
3. Append one line to `progress/changelog.md`.
4. Create or update memory only when something non-obvious was learned.
5. Run `scripts/lint_repo.sh` if it exists and summarize the result.
6. Check `git status`, stage the task's changed files, and create one git commit before the final reply.

### Removing or renaming a module

- **Remove**: move its spec to `spec/_archive/`, remove or mark the `status.md` row, delete source annotations that reference the removed spec, and add a changelog entry.
- **Rename**: update the spec path, source annotations if present, the `status.md` row, and any ancestor-spec references.
