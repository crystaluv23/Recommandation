# Recommandation - Session Entry Point

> Read this file first at the start of every session. It should take under 2 minutes.

## What this project is

The product target is intentionally pending. The user will define it later.

Until then, preserve the meta mechanism and avoid importing assumptions from the source project this setup was migrated from.

-> See [`spec/vision.md`](spec/vision.md) for goals, non-goals, and design principles once the target is known.
-> See [`spec/architecture.md`](spec/architecture.md) for the top-level design once it has been drafted.

## Where things stand right now

-> See [`progress/status.md`](progress/status.md) for current done / doing / blocked / next.

## Memory (load on demand)

Accumulated experience and meta-learning live in `memory/`. When prior experience might apply, read [`memory/GUIDE.md`](memory/GUIDE.md) - it contains the index and protocol. Do not read it at session start.

---

## File Architecture

```text
AGENTS.md                   <- you are here (session entry point)
spec/                       <- design layer (hierarchical, module-level)
  vision.md                 <- goals, non-goals, principles; target pending
  architecture.md           <- top-level framework design; target pending
  README.md                 <- spec conventions
  src/                      <- mirrors src/ at package/module granularity once source exists
memory/                     <- accumulated learning (read on demand, not by default)
  GUIDE.md                  <- entry point: experience index + visit_times protocol
  experiences/              <- concrete lessons: bugs, anti-patterns, decisions
  meta/
    insights.md             <- distilled project-specific advice
    usage_log.md            <- raw log of experience reads + meta-review records
progress/                   <- live project state
  status.md                 <- module-by-module progress table
  changelog.md              <- running log of meaningful changes
src/                        <- source code, once implementation begins
tests/                      <- tests, mirroring source structure when practical
```

## Core Conventions

**Target discipline:**
Do not assume the domain, runtime, architecture, or package layout before the user defines the project target. It is fine to prepare meta files, but product specs and code should wait for the target or be clearly labeled as placeholders.

**Spec hierarchy:**
`spec/vision.md` -> `spec/architecture.md` -> module specs under `spec/src/` -> sub-module specs.
Each level is progressively more concrete. Once source code exists, module specs should be written or expanded before implementation begins.

**Tree consistency rule:**
If a proposed spec change conflicts with a constraint in an ancestor spec (`architecture.md` or `vision.md`), stop. Name the exact ancestor level where the conflict arises, explain it to the user, and wait for confirmation before proceeding. Propagate confirmed changes top-down.

**Sync discipline:**
If design changes mid-session, update the spec first or simultaneously. Spec and code diverging within a session is a bug. If code changes are exploratory, backfill the spec before ending the session.

**Before implementing:**
State assumptions explicitly. If the target or user intent is still genuinely unclear, ask one focused question. If a simple conservative interpretation is available, use it and document the assumption.

**Code quality norms:**
- Write the minimum code that solves the problem. No abstractions for single-use code, no "flexibility" that was not requested.
- Keep modules loosely coupled and shaped around explicit interfaces.
- Names should reveal intention at the shortest length that is unambiguous in context.
- Match the repository's established style once code exists.
- Add tests in proportion to risk and blast radius.

**Dependency hygiene:**
When a runtime and packaging format exist, keep dependency declarations as the source of truth for that ecosystem. Do not leave undeclared runtime imports or packages. If the target later becomes Python, prefer `pyproject.toml` as the canonical runtime dependency declaration and keep `requirements.txt` thin if one is used.

**Surgical changes:**
Touch only what the task requires. Do not improve adjacent code, comments, or formatting. Remove dead code and redundancy that your changes created. For pre-existing unrelated issues, mention them rather than fixing them silently.

**Memory protocol:**
Do not read memory at session start. When you encounter a situation where prior experience might apply, open `memory/GUIDE.md` and follow the consultation protocol. When starting work on a specific module after modules exist, do a quick trigger-map scan before diving in.

**Progress hygiene:**
For any session where code or design changes, fix spec drift, update `progress/status.md`, append a line to `progress/changelog.md`, and add memory only for non-obvious lessons likely to matter later.

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

### Removing or renaming a module

- **Remove**: move its spec to `spec/_archive/`, remove or mark the `status.md` row, delete source annotations that reference the removed spec, and add a changelog entry.
- **Rename**: update the spec path, source annotations if present, the `status.md` row, and any ancestor-spec references.
