# Spec Isomorphism Guide

Specs are the design layer for this repository. They are hierarchical, module-level, and kept in sync with code once code exists.

## Hierarchy

```text
spec/vision.md
  -> spec/architecture.md
    -> spec/src/<package>/<module>.md
      -> spec/src/<package>/<module>/<submodule>.md
```

Each lower level is more concrete and must stay consistent with its ancestors.

`spec/src/` mirrors `src/` at package and module granularity once source exists.

## Granularity

Use one spec per module, not one spec per file. Split into `spec/src/<package>/<module>/<submodule>.md` only when:

- the submodule exposes an interface another module can depend on, or
- the module spec grows beyond about 150 lines and clearly separates into independent concerns.

If neither condition holds, keep the module spec flat.

## Module Spec Template

```markdown
# <Module Name>

## Status
Not started | Doing | Done | Blocked

## Purpose
What this module is responsible for, and why it exists.

## External Interface
What other modules may depend on.

## Responsibilities
- What this module owns.
- What it must not own.

## Dependencies
- Upstream modules this module may consume.
- Downstream modules this module serves.

## Invariants
- Rules that must remain true across implementations.

## Testing
How this module should be verified when code exists.
```

## Current Stage

Only the meta mechanism has been initialized. The product target is pending, so `vision.md` and `architecture.md` are placeholders until the user defines the target.

## Sync Rules

- Write or expand the relevant module spec before implementation.
- If code behavior changes, update the spec in the same session.
- If a module is renamed or removed, update spec paths, source annotations if present, `progress/status.md`, and any ancestor references.
- If a proposed module design conflicts with `spec/architecture.md` or `spec/vision.md`, stop and ask for confirmation before changing ancestors.
